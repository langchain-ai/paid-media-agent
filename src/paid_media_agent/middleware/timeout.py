"""Hard cap on one model call, independent of the provider SDK.

A streamed gateway response can stall after headers without tripping the SDK's read timeout.
Cancelling the call here turns a silent multi-minute hang into a retryable failure.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest


class ModelTimeoutMiddleware(AgentMiddleware[Any, Any, Any]):
    name = "PaidMediaModelTimeout"

    def __init__(self, seconds: float) -> None:
        super().__init__()
        self._seconds = seconds

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        # Sync calls cannot be cancelled safely; the SDK timeout is the only bound there.
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[Any]],
    ) -> Any:
        try:
            return await asyncio.wait_for(handler(request), timeout=self._seconds)
        except TimeoutError:
            raise TimeoutError(f"model call exceeded {self._seconds:.0f} seconds") from None
