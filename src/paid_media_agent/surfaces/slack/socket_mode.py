"""One async Bolt app for Socket Mode and signed HTTP."""

from __future__ import annotations

from typing import Any

from paid_media_agent.config import Settings
from paid_media_agent.surfaces.slack.blocks import ACTION_APPROVE, ACTION_REJECT
from paid_media_agent.surfaces.slack.delivery import deliver
from paid_media_agent.surfaces.slack.service import SlackApplicationService, build_slack_service


def build_bolt_app(settings: Settings, service: SlackApplicationService) -> Any:
    from slack_bolt.async_app import AsyncApp
    from slack_sdk.http_retry.builtin_async_handlers import AsyncRateLimitErrorRetryHandler
    from slack_sdk.web.async_client import AsyncWebClient

    if settings.slack_bot_token is None:
        raise ValueError("SLACK_BOT_TOKEN is not configured")
    client = AsyncWebClient(token=settings.slack_bot_token.get_secret_value())
    client.retry_handlers.append(AsyncRateLimitErrorRetryHandler(max_retry_count=2))
    app = AsyncApp(
        client=client,
        process_before_response=False,
        signing_secret=settings.slack_signing_secret.get_secret_value()
        if settings.slack_signing_secret
        else None,
    )

    @app.event("app_mention")
    @app.event("message")
    async def _on_message(body: dict[str, Any], client: Any) -> None:
        await deliver(service, client, body)

    @app.action({"action_id": ACTION_APPROVE})
    @app.action({"action_id": ACTION_REJECT})
    async def _on_action(ack: Any, body: dict[str, Any], client: Any) -> None:
        await ack()
        await deliver(service, client, body, action=True)

    return app


async def run_socket_mode(settings: Settings, runtime: Any) -> None:
    from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

    if settings.slack_app_token is None:
        raise ValueError("SLACK_APP_TOKEN is not configured")
    app = build_bolt_app(settings, build_slack_service(runtime))
    handler: Any = AsyncSocketModeHandler(app, settings.slack_app_token.get_secret_value())
    await handler.start_async()
