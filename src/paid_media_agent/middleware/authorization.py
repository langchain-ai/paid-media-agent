"""Invocation guard: the tool surface the model can see and call is decided here, not by prompts."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command
from pydantic import BaseModel, ConfigDict

from paid_media_agent.tools.catalog import CatalogProvider, ToolClass

logger = logging.getLogger(__name__)

# Deep Agents built-ins that this product never exposes: no subagent tier, no shell, no deletes.
HIDDEN_BUILTIN_TOOLS: frozenset[str] = frozenset({"task", "execute", "delete"})


class ToolSurfacePolicy(BaseModel):
    """Names the model may call. Anything else is denied even if a framework registered it."""

    model_config = ConfigDict(frozen=True)

    allowed_tool_names: frozenset[str]
    hidden_tool_names: frozenset[str] = HIDDEN_BUILTIN_TOOLS

    def allows(self, name: str) -> bool:
        return name in self.allowed_tool_names and name not in self.hidden_tool_names


def _denied(request: ToolCallRequest, reason: str) -> ToolMessage:
    body = {"denied": True, "reason": reason, "tool": request.tool_call["name"]}
    return ToolMessage(
        content=json.dumps(body),
        tool_call_id=request.tool_call["id"],
        name=request.tool_call["name"],
        status="error",
    )


class InvocationGuardMiddleware(AgentMiddleware[Any, Any, Any]):
    """Hides unsupported built-ins from the model and denies calls outside the surface policy."""

    name = "PaidMediaInvocationGuard"

    def __init__(self, *, surface: ToolSurfacePolicy, catalog_provider: CatalogProvider) -> None:
        super().__init__()
        self._surface = surface
        self._catalog_provider = catalog_provider
        self.denials: list[tuple[str, str]] = []

    def _filter_tools(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        kept: list[BaseTool | dict[str, Any]] = []
        for tool in request.tools:
            if isinstance(tool, BaseTool) and not self._surface.allows(tool.name):
                continue
            kept.append(tool)
        if len(kept) == len(request.tools):
            return request
        return request.override(tools=kept)

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return handler(self._filter_tools(request))

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return await handler(self._filter_tools(request))

    def _check(self, request: ToolCallRequest) -> ToolMessage | None:
        name = request.tool_call["name"]
        if not self._surface.allows(name):
            self.denials.append((name, "outside_tool_surface"))
            logger.warning("denied tool call outside surface: %s", name)
            return _denied(
                request, "tool is not part of the authorized surface; use discover_tools"
            )
        entry = self._catalog_provider.current().get(name)
        if entry is not None and entry.tool_class is not ToolClass.READ:
            self.denials.append((name, "mutation_or_denied_class"))
            logger.warning("denied direct call to non-read catalog entry: %s", name)
            return _denied(
                request, "provider mutations run only through propose_change and execute_change"
            )
        return None

    def wrap_tool_call(self, request: ToolCallRequest, handler: Any) -> ToolMessage | Command[Any]:
        denial = self._check(request)
        return denial if denial is not None else handler(request)

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Any
    ) -> ToolMessage | Command[Any]:
        denial = self._check(request)
        return denial if denial is not None else await handler(request)
