"""Socket Mode transport for local and private deployments. No public endpoint required."""

from __future__ import annotations

import asyncio
from typing import Any

from paid_media_agent.config import Settings
from paid_media_agent.surfaces.slack.blocks import ACTION_APPROVE, ACTION_EDIT, ACTION_REJECT
from paid_media_agent.surfaces.slack.service import (
    SlackApplicationService,
    SlackReply,
    build_slack_service,
)


def post_reply(client: Any, reply: SlackReply) -> None:
    """Post a reply into its thread; shared by both transports."""
    client.chat_postMessage(
        channel=reply.channel,
        thread_ts=reply.thread_ts,
        text=reply.message.text,
        blocks=list(reply.message.blocks),
    )


def build_bolt_app(settings: Settings, service: SlackApplicationService) -> Any:
    from slack_bolt import App

    if settings.slack_bot_token is None:
        raise ValueError("SLACK_BOT_TOKEN is not configured")
    from slack_sdk import WebClient
    from slack_sdk.http_retry.builtin_handlers import RateLimitErrorRetryHandler

    client = WebClient(token=settings.slack_bot_token.get_secret_value())
    # The bare SDK client has no 429 handling; honor Retry-After a bounded number of times.
    client.retry_handlers.append(RateLimitErrorRetryHandler(max_retry_count=2))
    app = App(
        client=client,
        signing_secret=settings.slack_signing_secret.get_secret_value()
        if settings.slack_signing_secret
        else None,
    )

    @app.event("app_mention")
    def _on_mention(body: dict[str, Any], client: Any) -> None:
        reply = asyncio.run(service.handle_event(body))
        if reply is not None:
            post_reply(client, reply)

    @app.event("message")
    def _on_message(body: dict[str, Any], client: Any) -> None:
        reply = asyncio.run(service.handle_event(body))
        if reply is not None:
            post_reply(client, reply)

    @app.action({"action_id": ACTION_APPROVE})
    @app.action({"action_id": ACTION_REJECT})
    @app.action({"action_id": ACTION_EDIT})
    def _on_action(ack: Any, body: dict[str, Any], client: Any) -> None:
        ack()
        reply = asyncio.run(service.handle_action(body))
        if reply is not None:
            post_reply(client, reply)

    return app


def run_socket_mode(settings: Settings, runtime: Any) -> None:
    from slack_bolt.adapter.socket_mode import SocketModeHandler

    if settings.slack_app_token is None:
        raise ValueError("SLACK_APP_TOKEN is not configured")
    app = build_bolt_app(settings, build_slack_service(runtime))
    handler: Any = SocketModeHandler(app, settings.slack_app_token.get_secret_value())
    handler.start()
