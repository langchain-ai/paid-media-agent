"""Secret redaction for tool results, errors, and logs."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

REDACTED = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bxapp-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bpb_[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)(api[_-]?key|token|secret|password|authorization)\s*[:=]\s*['\"]?[A-Za-z0-9\-._~+/]{12,}['\"]?"
    ),
    re.compile(r"(?i)postgres(?:ql)?://[^\s'\"]+"),
)


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    """Remove known secret values and credential-shaped substrings."""
    result = text
    for secret in secrets:
        if secret and len(secret) >= 6:
            result = result.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        result = pattern.sub(REDACTED, result)
    return result


def sanitize_exception(exc: BaseException, secrets: Sequence[str] = ()) -> str:
    """Return a bounded, redacted, one-line description that is safe for the model."""
    text = f"{type(exc).__name__}: {exc}"
    text = text.replace("\n", " ")
    return redact(text, secrets)[:400]


class RedactionMiddleware(AgentMiddleware[Any, Any, Any]):
    """Redacts secrets from every tool result before it reaches the model."""

    name = "PaidMediaRedaction"

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        super().__init__()
        self._secrets = tuple(secrets)

    def _clean(self, result: ToolMessage | Command[Any]) -> ToolMessage | Command[Any]:
        if isinstance(result, ToolMessage) and isinstance(result.content, str):
            cleaned = redact(result.content, self._secrets)
            if cleaned != result.content:
                return result.model_copy(update={"content": cleaned})
        return result

    def wrap_tool_call(self, request: ToolCallRequest, handler: Any) -> ToolMessage | Command[Any]:
        try:
            return self._clean(handler(request))
        except Exception as exc:  # noqa: BLE001 - every tool error is sanitized for the model
            return ToolMessage(
                content=f"Tool failed: {sanitize_exception(exc, self._secrets)}",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
                status="error",
            )

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Any
    ) -> ToolMessage | Command[Any]:
        try:
            return self._clean(await handler(request))
        except Exception as exc:  # noqa: BLE001
            return ToolMessage(
                content=f"Tool failed: {sanitize_exception(exc, self._secrets)}",
                tool_call_id=request.tool_call["id"],
                name=request.tool_call["name"],
                status="error",
            )
