"""Deterministic Block Kit renderers. Model text is escaped and bounded; values are opaque ids."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.presentation import (
    ProposalView,
    ReceiptView,
    ReportSummary,
)

SECTION_TEXT_LIMIT = 3000
HEADER_TEXT_LIMIT = 150
BLOCK_LIMIT = 50
ACTION_APPROVE = "pma_approve"
ACTION_REJECT = "pma_reject"
ACTION_EDIT = "pma_edit"


class SlackMessage(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(description="Accessible fallback text. Always present.")
    blocks: tuple[dict[str, Any], ...]


def escape_mrkdwn(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bounded_mrkdwn(text: str, limit: int = SECTION_TEXT_LIMIT) -> str:
    escaped = escape_mrkdwn(text)
    if len(escaped) <= limit:
        return escaped
    return escaped[: limit - 1] + "…"


def _section(text: str) -> dict[str, Any]:
    return {"type": "section", "text": {"type": "mrkdwn", "text": bounded_mrkdwn(text)}}


def _header(text: str) -> dict[str, Any]:
    return {
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": escape_mrkdwn(text)[:HEADER_TEXT_LIMIT],
            "emoji": False,
        },
    }


def _context(text: str) -> dict[str, Any]:
    return {"type": "context", "elements": [{"type": "mrkdwn", "text": bounded_mrkdwn(text, 2000)}]}


def _button(label: str, action_id: str, value: str, style: str | None = None) -> dict[str, Any]:
    button: dict[str, Any] = {
        "type": "button",
        "text": {"type": "plain_text", "text": label, "emoji": False},
        "action_id": action_id,
        "value": value,
    }
    if style:
        button["style"] = style
    return button


def _finish(text: str, blocks: list[dict[str, Any]]) -> SlackMessage:
    return SlackMessage(text=text[:SECTION_TEXT_LIMIT], blocks=tuple(blocks[:BLOCK_LIMIT]))


_HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.M)
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RULE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$", re.M)


def to_mrkdwn(text: str) -> str:
    """Slack shows markdown literally; fold the common forms into mrkdwn so a stray one still reads."""
    text = _HEADING.sub(lambda m: f"*{m.group(1).strip()}*", text)
    text = _BOLD.sub(r"*\1*", text)
    text = _RULE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def render_answer(text: str) -> SlackMessage:
    """Plain model answer. One section per paragraph, bounded."""
    text = to_mrkdwn(text)
    paragraphs = [p for p in text.split("\n\n") if p.strip()] or [text]
    blocks = [_section(p) for p in paragraphs[: BLOCK_LIMIT - 1]]
    return _finish(text, blocks)


def render_proposal(view: ProposalView, *, can_act: bool) -> SlackMessage:
    before = (
        ", ".join(
            f"{fv.field}={fv.value}" + (f" {fv.unit}" if fv.unit else "") for fv in view.before
        )
        or "n/a"
    )
    after = (
        ", ".join(
            f"{fv.field}={fv.value}" + (f" {fv.unit}" if fv.unit else "") for fv in view.after
        )
        or "n/a"
    )
    summary = (
        f"Proposal {view.proposal_id} (revision {view.revision}, {view.state.value})\n"
        f"Platform: {view.platform.value} · Account: {view.account_ref} · Tool: {view.tool_name}\n"
        f"Target: {view.target_ref}\nBefore: {before}\nAfter: {after}\nRisk: {view.risk.value}"
        + (f" [{', '.join(view.risk_flags)}]" if view.risk_flags else "")
    )
    blocks: list[dict[str, Any]] = [
        _header("Change proposal for review"),
        _section(summary),
        _section(f"*Reason*\n{view.reason}"),
    ]
    if view.measurement_plan or view.reversal_plan:
        blocks.append(
            _section(
                f"*Measurement*\n{view.measurement_plan or 'n/a'}\n*Reversal*\n{view.reversal_plan or 'n/a'}"
            )
        )
    blocks.append(
        _context(
            f"digest {view.payload_digest[:16]}… · catalog {view.catalog_revision} · requested by {view.requester_ref}"
        )
    )
    if can_act and view.state.value == "awaiting_approval":
        blocks.append(
            {
                "type": "actions",
                "block_id": f"pma_actions_{view.routing_id[:20]}",
                "elements": [
                    _button("Approve", ACTION_APPROVE, view.routing_id, "primary"),
                    _button("Edit", ACTION_EDIT, view.routing_id),
                    _button("Reject", ACTION_REJECT, view.routing_id, "danger"),
                ],
            }
        )
    return _finish(summary, blocks)


def render_receipt(view: ReceiptView) -> SlackMessage:
    state = (
        ", ".join(f"{fv.field}={fv.value}" for fv in view.verified_state) or "no verified fields"
    )
    text = (
        f"Receipt for proposal {view.proposal_id} revision {view.revision}: {view.status.upper()}\n"
        f"Mutation attempted: {'yes' if view.mutation_attempted else 'no'} · provider acknowledged: "
        f"{'yes' if view.provider_acknowledged else 'no'} · readback attempts: {view.readback_attempts}\n"
        f"Verified state: {state}\nReason: {view.reason}"
    )
    header = {
        "verified": "Change verified",
        "rejected": "Change rejected",
        "failed": "Change failed",
        "unknown": "Change outcome unknown",
    }
    blocks = [_header(header.get(view.status, "Change receipt")), _section(text)]
    if view.status == "unknown":
        blocks.append(
            _context(
                "Do not retry blindly. Reconcile with a read-only check or open a new proposal."
            )
        )
    return _finish(text, blocks)


def render_report(summary: ReportSummary) -> SlackMessage:
    scorecard = (
        "\n".join(f"• {label}: {value}" for label, value in summary.scorecard)
        or "Cross-platform total suppressed."
    )
    text = f"{summary.title}\n{summary.scope}\n\n{summary.executive_summary}"
    blocks = [
        _header(summary.title),
        _context(summary.scope),
        _section(summary.executive_summary),
        _section(f"*Scorecard*\n{scorecard}"),
        _section("*Platforms*\n" + "\n".join(f"• {line}" for line in summary.platform_lines)),
        _section("*Data quality*\n" + "\n".join(f"• {line}" for line in summary.data_quality)),
        _context(
            f"reconciled={'yes' if summary.reconciled else 'no'} · files: {', '.join(summary.artifact_paths) or 'none'}"
        ),
    ]
    return _finish(text, blocks)
