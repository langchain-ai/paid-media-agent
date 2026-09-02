"""Tell the model what day it is. Relative windows ("last week") are otherwise guesses."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import SystemMessage


class CurrentDateMiddleware(AgentMiddleware[Any, Any, Any]):
    """Append the current UTC date to the system message on every model call.

    Long-lived servers build the graph once, so the date is read per call rather than baked
    into the prompt. Deterministic code still owns every window calculation; this only stops
    the model from assuming a training-time year when it picks a date range.
    """

    name = "PaidMediaCurrentDate"

    def __init__(self, now: Callable[[], datetime] | None = None) -> None:
        super().__init__()
        self._now = now or (lambda: datetime.now(UTC))

    def _stamp(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        today = self._now().date().isoformat()
        line = f"Current date (UTC): {today}. Resolve relative windows from this date."
        existing = request.system_message
        if existing is None:
            return request.override(system_message=SystemMessage(content=line))
        content = existing.content
        if isinstance(content, str):
            merged: Any = f"{content.rstrip()}\n\n{line}"
        else:
            merged = [*content, {"type": "text", "text": line}]
        return request.override(system_message=SystemMessage(content=merged))

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return handler(self._stamp(request))

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return await handler(self._stamp(request))
