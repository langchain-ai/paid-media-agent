"""Host-side Pipeboard Streamable HTTP MCP loading and read execution."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Mapping
from typing import Any

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
)
from paid_media_agent.tools.providers import ProviderError, ProviderResult, ProviderTimeout

logger = logging.getLogger(__name__)

PIPEBOARD_SOURCE = "pipeboard"
STREAMABLE_HTTP = "streamable_http"


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
    """Loads the authenticated catalog host-side and caches it for a bounded period."""

    def __init__(
        self,
        *,
        settings: Settings,
        policy: LocalPolicy = DEFAULT_LOCAL_POLICY,
        ttl_seconds: int | None = None,
    ) -> None:
        if settings.pipeboard_api_token is None:
            raise ValueError("PIPEBOARD_API_TOKEN is not configured")
        self._settings = settings
        self._policy = policy
        self._ttl = ttl_seconds or settings.paid_media_catalog_ttl_seconds
        self._catalog: AuthorizedToolCatalog | None = None
        self._loaded_at = 0.0
        self._tools_by_name: dict[str, BaseTool] = {}

    def current(self) -> AuthorizedToolCatalog:
        if self._catalog is None:
            raise RuntimeError("catalog not loaded; call refresh() first")
        return self._catalog

    @property
    def expired(self) -> bool:
        return self._catalog is None or (time.monotonic() - self._loaded_at) > self._ttl

    async def refresh(self) -> AuthorizedToolCatalog:
        from langchain_mcp_adapters.client import MultiServerMCPClient  # noqa: PLC0415

        token = self._settings.pipeboard_api_token
        assert token is not None  # noqa: S101 - checked in __init__
        endpoints = self._settings.pipeboard_endpoints()
        client = MultiServerMCPClient(pipeboard_connections(endpoints, token))  # type: ignore[arg-type]
        raw_tools: list[RawTool] = []
        tools_by_name: dict[str, BaseTool] = {}
        for platform, url in endpoints.items():
            try:
                tools = await client.get_tools(server_name=platform.value)
            except Exception as exc:  # noqa: BLE001 - one platform failing must not hide the others
                logger.warning(
                    "catalog load failed for %s: %s", platform.value, sanitize_exception(exc)
                )
                continue
            raw_tools.extend(raw_tools_from_langchain(platform.value, url, tools))
            for tool in tools:
                tools_by_name[f"{platform.value}__{tool.name}"] = tool
        catalog = build_authorized_catalog(raw_tools, policy=self._policy, source=PIPEBOARD_SOURCE)
        self._catalog = catalog
        self._tools_by_name = tools_by_name
        self._loaded_at = time.monotonic()
        return catalog

    def langchain_tool(self, qualified_name: str) -> BaseTool | None:
        return self._tools_by_name.get(qualified_name)


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
        try:
            result = await asyncio.wait_for(tool.ainvoke(dict(arguments)), timeout=self._timeout)
        except TimeoutError as exc:
            raise ProviderTimeout("provider read timed out") from exc
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(sanitize_exception(exc)) from None
        payload = _payload_from_result(result)
        return ProviderResult(payload=payload)


def _payload_from_result(result: Any) -> dict[str, JsonValue]:
    """Coerce MCP content into a JSON object. Text results are parsed when they are JSON."""
    import json  # noqa: PLC0415

    if isinstance(result, tuple) and len(result) == 2:
        content, artifact = result
        structured = getattr(artifact, "structured_content", None)
        if isinstance(structured, dict):
            return structured
        result = content
    if isinstance(result, dict):
        return result
    if isinstance(result, list):
        texts = [item.get("text", "") if isinstance(item, dict) else str(item) for item in result]
        result = "\n".join(t for t in texts if t)
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return {"text": result}
        if isinstance(parsed, dict):
            return parsed
        return {"items": parsed}
    return {"text": str(result)}
