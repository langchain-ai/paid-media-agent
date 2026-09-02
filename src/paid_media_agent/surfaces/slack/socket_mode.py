"""Socket Mode transport for local and private deployments. No public endpoint required."""

from __future__ import annotations

import asyncio
from typing import Any

from paid_media_agent.config import Settings
from paid_media_agent.surfaces.runner import AgentRunner
from paid_media_agent.surfaces.slack.service import SlackApplicationService, SlackReply


def _post(client: Any, reply: SlackReply) -> None:
    client.chat_postMessage(
        channel=reply.channel,
        thread_ts=reply.thread_ts,
        text=reply.message.text,
        blocks=list(reply.message.blocks),
    )


def build_bolt_app(settings: Settings, service: SlackApplicationService) -> Any:
    from slack_bolt import App  # noqa: PLC0415

    if settings.slack_bot_token is None:
        raise ValueError("SLACK_BOT_TOKEN is not configured")
    app = App(
        token=settings.slack_bot_token.get_secret_value(),
        signing_secret=settings.slack_signing_secret.get_secret_value()
        if settings.slack_signing_secret
        else None,
    )

    @app.event("app_mention")
    def _on_mention(body: dict[str, Any], client: Any) -> None:
        reply = asyncio.run(service.handle_event(body))
        if reply is not None:
            _post(client, reply)

    @app.event("message")
    def _on_message(body: dict[str, Any], client: Any) -> None:
        reply = asyncio.run(service.handle_event(body))
        if reply is not None:
            _post(client, reply)

    @app.action({"action_id": "pma_approve"})
    @app.action({"action_id": "pma_reject"})
    @app.action({"action_id": "pma_edit"})
    @app.action({"action_id": "pma_cancel"})
    def _on_action(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        reply = asyncio.run(service.handle_action(body))
        if reply is not None:
            _post(client, reply)

    return app


def run_socket_mode(settings: Settings, runtime: Any) -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler  # noqa: PLC0415

    if settings.slack_app_token is None:
        raise ValueError("SLACK_APP_TOKEN is not configured")
    runner = AgentRunner(
        graph=runtime.graph,
        service=runtime.components.proposal_service,
        receipts=runtime.profile.receipts,
        threads=runtime.threads,
    )
    service = SlackApplicationService(runner=runner, dedupe=runtime.dedupe)
    app = build_bolt_app(settings, service)
    handler: Any = SocketModeHandler(app, settings.slack_app_token.get_secret_value())
    handler.start()
