"""Signed HTTP transport: verify Slack signatures and route to the application service."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs

from paid_media_agent.surfaces.slack.service import SlackApplicationService, SlackReply

REPLAY_WINDOW_SECONDS = 300


class SlackSignatureError(Exception):
    pass


def verify_signature(
    *, signing_secret: str, body: bytes, headers: Mapping[str, str], now: float | None = None
) -> None:
    """Raise unless the request carries a fresh, valid Slack signature."""
    from slack_sdk.signature import SignatureVerifier

    timestamp = headers.get("x-slack-request-timestamp") or headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("x-slack-signature") or headers.get("X-Slack-Signature")
    if not timestamp or not signature:
        raise SlackSignatureError("missing signature headers")
    try:
        ts = int(timestamp)
    except ValueError as exc:
        raise SlackSignatureError("malformed timestamp") from exc
    current = now if now is not None else time.time()
    if abs(current - ts) > REPLAY_WINDOW_SECONDS:
        raise SlackSignatureError("request timestamp outside the replay window")
    verifier = SignatureVerifier(signing_secret)
    if not verifier.is_valid(body, timestamp, signature):
        raise SlackSignatureError("invalid signature")


def parse_request(body: bytes, content_type: str) -> dict[str, Any]:
    if content_type.startswith("application/x-www-form-urlencoded"):
        form = parse_qs(body.decode("utf-8"))
        payload = form.get("payload", [""])[0]
        parsed = json.loads(payload) if payload else {}
        return parsed if isinstance(parsed, dict) else {}
    parsed = json.loads(body.decode("utf-8") or "{}")
    return parsed if isinstance(parsed, dict) else {}


class SlackHttpTransport:
    def __init__(self, *, signing_secret: str, service: SlackApplicationService) -> None:
        self._secret = signing_secret
        self._service = service

    async def handle(
        self, *, body: bytes, headers: Mapping[str, str], content_type: str
    ) -> tuple[int, dict[str, Any], SlackReply | None]:
        """Return (status, response body, reply). URL verification is answered without running anything."""
        verify_signature(signing_secret=self._secret, body=body, headers=headers)
        payload = parse_request(body, content_type)
        if payload.get("type") == "url_verification":
            return 200, {"challenge": payload.get("challenge", "")}, None
        if payload.get("type") == "event_callback":
            reply = await self._service.handle_event(payload)
            return 200, {}, reply
        if payload.get("type") == "block_actions":
            reply = await self._service.handle_action(payload)
            return 200, {}, reply
        return 200, {}, None
