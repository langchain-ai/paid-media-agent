"""Offloads oversized tool results to workspace artifacts and returns a compact stub."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from paid_media_agent.tools.artifacts import ArtifactStore

OFFLOAD_SCHEMA_VERSION = "tool-result/1"
PREVIEW_CHARS = 400


class ResultOffloadMiddleware(AgentMiddleware[Any, Any, Any]):
    name = "PaidMediaResultOffload"

    def __init__(self, artifacts: ArtifactStore, *, max_chars: int) -> None:
        super().__init__()
        self._artifacts = artifacts
        self._max_chars = max_chars

    def _offload(
        self, request: ToolCallRequest, result: ToolMessage | Command[Any]
    ) -> ToolMessage | Command[Any]:
        if not isinstance(result, ToolMessage) or not isinstance(result.content, str):
            return result
        if len(result.content) <= self._max_chars:
            return result
        metadata = self._artifacts.write_json(
            "tool_result",
            {"tool_name": request.tool_call["name"], "content": result.content},
            schema_version=OFFLOAD_SCHEMA_VERSION,
            tool_name=request.tool_call["name"],
        )
        stub = {
            "offloaded": True,
            "artifact_id": metadata.artifact_id,
            "byte_size": metadata.byte_size,
            "sha256": metadata.sha256,
            "preview": result.content[:PREVIEW_CHARS],
            "note": "Result exceeded the context budget. Use the artifact id with deterministic tools.",
        }
        return result.model_copy(update={"content": json.dumps(stub)})

    def wrap_tool_call(self, request: ToolCallRequest, handler: Any) -> ToolMessage | Command[Any]:
        return self._offload(request, handler(request))

    async def awrap_tool_call(
        self, request: ToolCallRequest, handler: Any
    ) -> ToolMessage | Command[Any]:
        # The artifact write touches disk and, in sandbox mode, the network: keep it off the loop.
        return await asyncio.to_thread(self._offload, request, await handler(request))
