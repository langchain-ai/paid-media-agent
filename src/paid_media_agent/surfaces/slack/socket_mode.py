"""Socket Mode transport for local and private deployments. No public endpoint required.

Async Bolt on the same event loop as the graph and the Postgres checkpointer; a sync handler per
event would need its own loop and could not share them.
"""

from __future__ import annotations

from typing import Any

from paid_media_agent.config import Settings
from paid_media_agent.surfaces.slack.blocks import ACTION_APPROVE, ACTION_EDIT, ACTION_REJECT
from paid_media_agent.surfaces.slack.service import (
    SlackApplicationService,
    SlackReply,
    build_slack_service,
)


def post_reply(client: Any, reply: SlackReply) -> None:
    """Post a reply into its thread with a synchronous client (the signed HTTP transport)."""
    client.chat_postMessage(
        channel=reply.channel,
        thread_ts=reply.thread_ts,
        text=reply.message.text,
        blocks=list(reply.message.blocks),
    )


async def post_reply_async(client: Any, reply: SlackReply) -> None:
    await client.chat_postMessage(
        channel=reply.channel,
        thread_ts=reply.thread_ts,
        text=reply.message.text,
        blocks=list(reply.message.blocks),
    )


def build_bolt_app(settings: Settings, service: SlackApplicationService) -> Any:
    from slack_bolt.async_app import AsyncApp
    from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
    from slack_sdk.web.async_client import AsyncWebClient

    if settings.slack_bot_token is None:
        raise ValueError("SLACK_BOT_TOKEN is not configured")
    client = AsyncWebClient(token=settings.slack_bot_token.get_secret_value())
    # The bare SDK client has no 429 handling; honor Retry-After a bounded number of times.
    client.retry_handlers.append(AsyncRateLimitErrorRetryHandler(max_retry_count=2))
    app = AsyncApp(
        client=client,
        signing_secret=settings.slack_signing_secret.get_secret_value()
        if settings.slack_signing_secret
        else None,
    )

    @app.event("app_mention")
    async def _on_mention(body: dict[str, Any], client: Any) -> None:
        reply = await service.handle_event(body)
        if reply is not None:
            await post_reply_async(client, reply)

    @app.event("message")
    async def _on_message(body: dict[str, Any], client: Any) -> None:
        reply = await service.handle_event(body)
        if reply is not None:
            await post_reply_async(client, reply)

    @app.action({"action_id": ACTION_APPROVE})
    @app.action({"action_id": ACTION_REJECT})
    @app.action({"action_id": ACTION_EDIT})
    async def _on_action(ack: Any, body: dict[str, Any], client: Any) -> None:
        await ack()
        reply = await service.handle_action(body)
        if reply is not None:
            await post_reply_async(client, reply)

    return app


async def run_socket_mode(settings: Settings, runtime: Any) -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    if settings.slack_app_token is None:
        raise ValueError("SLACK_APP_TOKEN is not configured")
    app = build_bolt_app(settings, build_slack_service(runtime))
    handler: Any = AsyncSocketModeHandler(app, settings.slack_app_token.get_secret_value())
    await handler.start_async()
