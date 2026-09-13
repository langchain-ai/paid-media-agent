"""Host-side Pipeboard Streamable HTTP MCP loading, read execution, and the live write adapter."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Mapping
from typing import Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from pydantic import SecretStr

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import JsonValue, Platform
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.tools.catalog import (
    DEFAULT_LOCAL_POLICY,
    AuthorizedToolCatalog,
    CatalogEntry,
    LocalPolicy,
    RawTool,
    build_authorized_catalog,
    qualified_name,
)
from paid_media_agent.tools.providers import ProviderError, ProviderResult, ProviderTimeout

logger = logging.getLogger(__name__)

PIPEBOARD_SOURCE = "pipeboard"
STREAMABLE_HTTP = "streamable_http"
CATALOG_LOAD_TIMEOUT_SECONDS = 20
_OPERATION_REF_KEYS = ("operation_ref", "operation_id", "resource_name", "id", "campaign_id")


def pipeboard_connections(
    endpoints: Mapping[Platform, str], token: SecretStr
) -> dict[str, dict[str, Any]]:
    """Connection map for `MultiServerMCPClient`. The bearer token lives only in this dict."""
    headers = {"Authorization": f"Bearer {token.get_secret_value()}"}
    return {
        platform.value: {"transport": STREAMABLE_HTTP, "url": url, "headers": headers}
        for platform, url in endpoints.items()
    }


def raw_tools_from_langchain(platform: str, endpoint: str, tools: list[BaseTool]) -> list[RawTool]:
    raw: list[RawTool] = []
    for tool in tools:
        schema = (
            tool.args_schema if isinstance(tool.args_schema, dict) else tool.get_input_jsonschema()
        )
        metadata = tool.metadata or {}
        annotations = {
            k: v
            for k, v in metadata.items()
            if k in ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint", "title")
        }
        raw.append(
            RawTool(
                platform=platform,
                name=tool.name,
                description=tool.description or "",
                input_schema=dict(schema),
                annotations=annotations if "readOnlyHint" in metadata else None,
                source_endpoint=endpoint,
            )
        )
    return raw


class PipeboardCatalogLoader:
    """Loads every server's tool catalog concurrently; keeps schemas host-side per assembly."""

    def __init__(
        self,
        *,
        settings: Settings,
        policy: LocalPolicy = DEFAULT_LOCAL_POLICY,
        extra_raw_tools: list[RawTool] | None = None,
    ) -> None:
        if settings.pipeboard_api_token is None:
            raise ValueError("PIPEBOARD_API_TOKEN is not configured")
        self._settings = settings
        self._policy = policy
        self._extra_raw_tools = list(extra_raw_tools or [])
        self._catalog: AuthorizedToolCatalog | None = None
        self._tools_by_name: dict[str, BaseTool] = {}

    @property
    def policy(self) -> LocalPolicy:
        return self._policy

    def current(self) -> AuthorizedToolCatalog:
        """The catalog from `refresh()`. Loaded once per process; restart to pick up changes."""
        if self._catalog is None:
            raise RuntimeError("catalog not loaded; call refresh() first")
        return self._catalog

    async def refresh(self) -> AuthorizedToolCatalog:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        token = self._settings.pipeboard_api_token
        assert token is not None  # noqa: S101 - checked in __init__
        endpoints = self._settings.pipeboard_endpoints()
        client = MultiServerMCPClient(pipeboard_connections(endpoints, token))  # type: ignore[arg-type]
        raw_tools: list[RawTool] = []
        tools_by_name: dict[str, BaseTool] = {}

        async def load_endpoint(platform: Platform) -> list[BaseTool]:
            try:
                return await asyncio.wait_for(
                    client.get_tools(server_name=platform.value),
                    timeout=CATALOG_LOAD_TIMEOUT_SECONDS,
                )
            except Exception as exc:
                logger.warning(
                    "catalog load failed for %s: %s", platform.value, sanitize_exception(exc)
                )
                return []

        loaded = await asyncio.gather(*(load_endpoint(p) for p in endpoints))
        for (platform, url), tools in zip(endpoints.items(), loaded, strict=True):
            raw_tools.extend(raw_tools_from_langchain(platform.value, url, tools))
            for tool in tools:
                # Catalog lookup keeps the first entry and denies duplicate qualified names.
                tools_by_name.setdefault(qualified_name(platform, tool.name), tool)
        catalog = build_authorized_catalog(
            [*raw_tools, *self._extra_raw_tools], policy=self._policy, source=PIPEBOARD_SOURCE
        )
        self._catalog = catalog
        self._tools_by_name = tools_by_name
        return catalog

    def langchain_tool(self, qualified_name: str) -> BaseTool | None:
        return self._tools_by_name.get(qualified_name)


async def invoke_mcp_tool(
    tool: BaseTool, arguments: dict[str, JsonValue], *, timeout: float
) -> dict[str, JsonValue]:
    """Invoke a loaded MCP tool as a tool call so structured content and error status are visible."""
    call = {"name": tool.name, "args": dict(arguments), "id": "host-call", "type": "tool_call"}
    try:
        message = await asyncio.wait_for(tool.ainvoke(call), timeout=timeout)
    except TimeoutError as exc:
        raise ProviderTimeout("provider call timed out") from exc
    except Exception as exc:
        raise ProviderError(sanitize_exception(exc)) from None
    if isinstance(message, ToolMessage):
        if message.status == "error":
            raise ProviderError(sanitize_exception(RuntimeError(str(message.content)[:300])))
        structured = getattr(message.artifact, "structured_content", None)
        if isinstance(structured, dict):
            return structured
        return _payload_from_content(message.content)
    return _payload_from_content(message)


def _payload_from_content(content: Any) -> dict[str, JsonValue]:
    """Coerce MCP content into a JSON object. Text results are parsed when they are JSON."""
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        texts = [item.get("text", "") if isinstance(item, dict) else str(item) for item in content]
        content = "\n".join(t for t in texts if t)
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {"text": content}
        if isinstance(parsed, dict):
            return parsed
        return {"items": parsed}
    return {"text": str(content)}


class PipeboardReadProvider:
    """Executes authorized reads through the loaded MCP tools. Never called for mutations."""

    def __init__(self, loader: PipeboardCatalogLoader, *, timeout_seconds: float = 60.0) -> None:
        self._loader = loader
        self._timeout = timeout_seconds

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        tool = self._loader.langchain_tool(entry.qualified_name)
        if tool is None:
            raise ProviderError("tool is not loaded in the current catalog")
        payload = await invoke_mcp_tool(tool, arguments, timeout=self._timeout)
        return ProviderResult(payload=payload)


class PipeboardWriteProvider:
    """Exact live mutation adapter. Reachable only through `WriteExecutor` behind `WriteGate`."""

    def __init__(self, loader: PipeboardCatalogLoader, *, timeout_seconds: float = 60.0) -> None:
        self._loader = loader
        self._timeout = timeout_seconds

    async def call_mutation(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        tool = self._loader.langchain_tool(entry.qualified_name)
        if tool is None:
            raise ProviderError("mutation tool is not loaded in the current catalog")
        if entry.read_only_hint is not False:
            raise ProviderError("refusing to mutate through a tool without readOnlyHint=false")
        payload = await invoke_mcp_tool(tool, arguments, timeout=self._timeout)
        for key in _OPERATION_REF_KEYS:
            value = payload.get(key)
            if value is not None and "operation_ref" not in payload:
                payload = {**payload, "operation_ref": str(value)}
                break
        return payload
