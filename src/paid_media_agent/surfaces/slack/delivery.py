"""Native Slack streaming for assistant text and generic tool progress."""

from __future__ import annotations

import logging
from typing import Any

from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.surfaces.runner import RunEvent
from paid_media_agent.surfaces.slack.service import SlackApplicationService, SlackReply

_LOG = logging.getLogger(__name__)


class SlackDelivery:
    def __init__(self, client: Any, *, channel: str, thread_ts: str, team: str, user: str) -> None:
        self.client = client
        self.channel = channel
        self.thread_ts = thread_ts
        self.team = team
        self.user = user
        self.stream: Any = None
        self.message_id = ""
        self.last_text = ""
        self.started = False
        self.tasks: dict[str, str] = {}

    async def event(self, event: RunEvent) -> None:
        if event.kind == "start":
            self.started = True
            await self.client.agents_sessions_setStatus(
                channel_id=self.channel,
                thread_ts=self.thread_ts,
                initiator_user_id=self.user,
                status="processing",
            )
            self.stream = self.client.chat_stream(
                channel=self.channel,
                thread_ts=self.thread_ts,
                recipient_team_id=self.team,
                recipient_user_id=self.user,
                task_display_mode="plan",
            )
        elif event.kind == "text":
            if event.id != self.message_id:
                if self.last_text:
                    await self.stream.append(markdown_text="\n\n")
                self.last_text = ""
                self.message_id = event.id
            self.last_text += event.text
            await self.stream.append(markdown_text=event.text)
        elif event.kind == "tool":
            from slack_sdk.models.messages.chunk import TaskUpdateChunk

            title = event.name.replace("_", " ")[:100]
            if event.status == "in_progress":
                self.tasks[event.id] = title
            else:
                self.tasks.pop(event.id, None)
            await self.stream.append(
                chunks=[
                    TaskUpdateChunk(
                        id=event.id,
                        title=title,
                        status=event.status,
                    )
                ]
            )

    async def finish(self, reply: SlackReply) -> None:
        if self.stream is None:
            await self.client.chat_postMessage(
                channel=reply.channel,
                thread_ts=reply.thread_ts,
                text=reply.message.text[:4000],
                blocks=[
                    {"type": "markdown", "text": reply.message.text[:12000]},
                    *reply.message.blocks,
                ],
                unfurl_links=False,
                unfurl_media=False,
            )
            return
        remaining = ""
        if reply.message.text.strip() != self.last_text.strip():
            remaining = ("\n\n" if self.last_text else "") + reply.message.text
        interrupted = bool(reply.outcome and reply.outcome.interrupted)
        await self.stream.stop(
            markdown_text=remaining,
            blocks=list(reply.message.blocks) or None,
            chunks=[
                {"type": "task_update", "id": id, "title": title, "status": "pending"}
                for id, title in self.tasks.items()
            ]
            if interrupted
            else None,
            session_status="suspended" if interrupted else "active",
        )

    async def fail(self) -> None:
        text = "The run could not finish. Try again or check the server logs."
        try:
            if self.stream is not None:
                await self.stream.stop(
                    markdown_text="\n\n" + text,
                    session_status="active",
                    chunks=[
                        {"type": "task_update", "id": id, "title": title, "status": "error"}
                        for id, title in self.tasks.items()
                    ]
                    or None,
                )
            else:
                await self.client.chat_postMessage(
                    channel=self.channel,
                    thread_ts=self.thread_ts,
                    text=text,
                )
        finally:
            if self.started:
                await self.client.agents_sessions_setStatus(
                    channel_id=self.channel,
                    thread_ts=self.thread_ts,
                    status="active",
                )


async def deliver(
    service: SlackApplicationService, client: Any, body: dict[str, Any], *, action: bool = False
) -> None:
    if action:
        channel = str((body.get("channel") or {}).get("id") or "")
        message = body.get("message") or {}
        thread_ts = str(message.get("thread_ts") or message.get("ts") or "")
        team = str((body.get("team") or {}).get("id") or "")
        user = str((body.get("user") or {}).get("id") or "")
    else:
        event = body.get("event") or {}
        channel = str(event.get("channel") or "")
        thread_ts = str(event.get("thread_ts") or event.get("ts") or "")
        team = str(body.get("team_id") or "")
        user = str(event.get("user") or "")
    if not all((channel, thread_ts, team, user)):
        return
    delivery = SlackDelivery(client, channel=channel, thread_ts=thread_ts, team=team, user=user)
    try:
        handler = service.handle_action if action else service.handle_event
        reply = await handler(body, on_event=delivery.event)
        if reply is not None:
            await delivery.finish(reply)
    except Exception as exc:
        _LOG.error("Slack run failed: %s", sanitize_exception(exc))
        try:
            await delivery.fail()
        except Exception as delivery_error:
            _LOG.error("Slack error delivery failed: %s", sanitize_exception(delivery_error))
