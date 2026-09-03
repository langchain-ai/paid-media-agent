"""Slack application service: dedupe, thread mapping, mention policy, and proposal actions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from paid_media_agent.persistence.interfaces import DedupeStore
from paid_media_agent.surfaces.runner import AgentRunner, RunOutcome, ThreadAccessDenied
from paid_media_agent.surfaces.slack.blocks import (
    ACTION_APPROVE,
    ACTION_EDIT,
    ACTION_REJECT,
    SlackMessage,
    render_answer,
    render_proposal,
    render_receipt,
)
from paid_media_agent.tools.writes import WriteDenied


@dataclass(frozen=True)
class SlackReply:
    channel: str
    thread_ts: str
    message: SlackMessage
    outcome: RunOutcome | None = None


def slack_thread_id(team_id: str, channel: str, thread_ts: str) -> str:
    """Stable graph thread id per Slack conversation. Opaque and non-reversible."""
    digest = hashlib.sha256(f"{team_id}:{channel}:{thread_ts}".encode()).hexdigest()[:24]
    return f"slack-{digest}"


def slack_caller_ref(team_id: str, user_id: str) -> str:
    return f"slack:{team_id}:{user_id}"


def strip_mention(text: str, bot_user_id: str | None) -> str:
    if bot_user_id:
        return text.replace(f"<@{bot_user_id}>", "").strip()
    return text.strip()


class SlackApplicationService:
    """Transport-neutral. Socket Mode and signed HTTP both call `handle_event` and `handle_action`."""

    def __init__(
        self,
        *,
        runner: AgentRunner,
        dedupe: DedupeStore,
        bot_user_id: str | None = None,
        approver_lookup: Any = None,
    ) -> None:
        self._runner = runner
        self._dedupe = dedupe
        self._bot_user_id = bot_user_id
        self._approver_lookup = approver_lookup

    def _caller(self, team_id: str, user_id: str) -> str:
        if self._approver_lookup is not None:
            mapped = self._approver_lookup(team_id, user_id)
            if isinstance(mapped, str) and mapped:
                return mapped
        return slack_caller_ref(team_id, user_id)

    async def handle_event(self, envelope: dict[str, Any]) -> SlackReply | None:
        event_id = str(envelope.get("event_id") or "")
        if not event_id or self._dedupe.seen(f"event:{event_id}"):
            return None
        event = envelope.get("event") or {}
        if event.get("bot_id") or event.get("subtype"):
            return None
        event_type = event.get("type")
        channel_type = event.get("channel_type")
        if event_type not in ("app_mention", "message"):
            return None
        if event_type == "message" and channel_type != "im":
            return None
        team_id = str(envelope.get("team_id") or event.get("team") or "team")
        channel = str(event.get("channel"))
        thread_ts = str(event.get("thread_ts") or event.get("ts"))
        user_id = str(event.get("user"))
        text = strip_mention(str(event.get("text") or ""), self._bot_user_id)
        if not text:
            return None
        thread_id = slack_thread_id(team_id, channel, thread_ts)
        caller = self._caller(team_id, user_id)
        edit = text.split(maxsplit=2)
        if len(edit) == 3 and edit[0].lower() == "edit":
            # The Edit button asks for `edit <field> <value>` in the thread; this is that reply.
            proposal = self._runner.latest_proposal(thread_id)
            if proposal is None:
                return SlackReply(channel, thread_ts, render_answer("No proposal is waiting here."))
            message = await self.handle_edit_command(
                routing_id=proposal.routing_id,
                team_id=team_id,
                user_id=user_id,
                field=edit[1],
                value=edit[2],
            )
            return SlackReply(channel, thread_ts, message)
        try:
            outcome = await self._runner.send(thread_id=thread_id, caller_ref=caller, text=text)
        except ThreadAccessDenied:
            return SlackReply(
                channel, thread_ts, render_answer("This thread belongs to another user.")
            )
        message = self._render_outcome(outcome)
        return SlackReply(channel, thread_ts, message, outcome)

    def _render_outcome(self, outcome: RunOutcome) -> SlackMessage:
        if outcome.interrupted and outcome.proposal is not None:
            return render_proposal(outcome.proposal, can_act=True)
        if outcome.receipt is not None and outcome.proposal is not None and not outcome.interrupted:
            if (
                outcome.receipt.revision == outcome.proposal.revision
                and outcome.proposal.state.value in ("verified", "failed", "unknown", "rejected")
            ):
                return render_receipt(outcome.receipt)
        return render_answer(outcome.text or "(no response)")

    async def handle_action(self, payload: dict[str, Any]) -> SlackReply | None:
        """Block action. Values are opaque routing ids; the host reloads the persisted proposal."""
        actions = payload.get("actions") or []
        if not actions:
            return None
        action = actions[0]
        action_id = str(action.get("action_id"))
        routing_id = str(action.get("value") or "")
        trigger = str(payload.get("trigger_id") or payload.get("action_ts") or "")
        if self._dedupe.seen(f"action:{action_id}:{routing_id}:{trigger}"):
            return None
        team_id = str((payload.get("team") or {}).get("id") or "team")
        user_id = str((payload.get("user") or {}).get("id") or "")
        channel = str((payload.get("channel") or {}).get("id") or "")
        thread_ts = str(
            (payload.get("message") or {}).get("thread_ts")
            or (payload.get("message") or {}).get("ts")
            or ""
        )
        actor = self._caller(team_id, user_id)
        proposal = self._runner.proposal_by_routing_id(routing_id)
        if proposal is None:
            return SlackReply(
                channel,
                thread_ts,
                render_answer("This proposal is no longer current. Ask for a fresh review."),
            )
        try:
            if action_id == ACTION_APPROVE:
                outcome = await self._runner.approve(
                    proposal_id=proposal.proposal_id, approver_ref=actor
                )
            elif action_id == ACTION_REJECT:
                outcome = await self._runner.reject(
                    proposal_id=proposal.proposal_id, actor_ref=actor, message="rejected in Slack"
                )
            elif action_id == ACTION_EDIT:
                return SlackReply(
                    channel,
                    thread_ts,
                    render_answer(
                        "Reply in this thread with the new value, e.g. `edit daily_budget 250`."
                    ),
                    None,
                )
            else:
                return None
        except WriteDenied as exc:
            return SlackReply(
                channel,
                thread_ts,
                render_answer(f"Action refused: {exc.reason}. {exc.detail}".strip()),
            )
        return SlackReply(channel, thread_ts, self._render_outcome(outcome), outcome)

    async def handle_edit_command(
        self, *, routing_id: str, team_id: str, user_id: str, field: str, value: str
    ) -> SlackMessage:
        proposal = self._runner.proposal_by_routing_id(routing_id)
        if proposal is None:
            return render_answer("This proposal is no longer current.")
        actor = self._caller(team_id, user_id)
        parsed: Any = value
        try:
            parsed = float(value) if "." in value else int(value)
        except ValueError:
            parsed = value
        try:
            view = self._runner.edit(
                proposal_id=proposal.proposal_id, editor_ref=actor, changes={field: parsed}
            )
        except WriteDenied as exc:
            return render_answer(f"Edit refused: {exc.reason}. {exc.detail}".strip())
        return render_proposal(view, can_act=True)


def build_slack_service(runtime: Any) -> SlackApplicationService:
    """One Slack service over a built runtime, shared by Socket Mode and the HTTP transport."""
    from paid_media_agent.surfaces.runner import AgentRunner

    runner = AgentRunner(
        graph=runtime.graph,
        service=runtime.components.proposal_service,
        receipts=runtime.profile.receipts,
        threads=runtime.threads,
    )
    return SlackApplicationService(runner=runner, dedupe=runtime.dedupe)
