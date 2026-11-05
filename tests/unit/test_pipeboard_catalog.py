"""Full Pipeboard discovery stays concurrent, searchable, and account-scoped."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import SecretStr

from paid_media_agent.config import AccountBinding, AccountRegistry, Settings
from paid_media_agent.domain.common import PIPEBOARD_PLATFORMS, Platform
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import DEFAULT_LOCAL_POLICY
from paid_media_agent.tools.discovery import build_discover_tools_tool
from paid_media_agent.tools.pipeboard import (
    PipeboardCatalogLoader,
    PipeboardReadProvider,
    invoke_mcp_tool,
    raw_tools_from_langchain,
    tools_from_client,
)
from paid_media_agent.tools.providers import ProviderError
from paid_media_agent.tools.reads import ReadDenied, ReadDispatcher, model_facing_schema

READ_ONLY = {"mcp": {"tool": {"annotations": {"read_only_hint": True}}}}


def _platform_by_url(settings: Settings) -> dict[str, str]:
    return {url: platform.value for platform, url in settings.pipeboard_endpoints().items()}


async def test_all_catalogs_load_concurrently_and_new_platforms_are_searchable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: set[str] = set()
    ready = asyncio.Event()
    calls: list[dict[str, Any]] = []

    async def report(**kwargs: Any) -> str:
        calls.append(kwargs)
        return json.dumps({"rows": [{"date": "2026-08-28", "sessions": 12}]})

    platforms = _platform_by_url(settings)

    async def load(url: str, headers: Any) -> list[BaseTool]:
        assert headers == {"Authorization": "Bearer test-token"}
        server_name = platforms[url]
        started.add(server_name)
        if len(started) == 8:
            ready.set()
        # A sequential loader cannot pass this barrier.
        await asyncio.wait_for(ready.wait(), timeout=1)
        policy = DEFAULT_LOCAL_POLICY.platform_policy(Platform(server_name))
        assert policy is not None
        account_arg = policy.account_arg_names[0]
        return [
            StructuredTool(
                name="get_current_report",
                description="Campaign and analytics reporting from the live catalog.",
                args_schema={
                    "type": "object",
                    "properties": {account_arg: {"type": "string"}},
                    "required": [account_arg],
                },
                metadata=READ_ONLY,
                coroutine=report,
            )
        ]

    loader = PipeboardCatalogLoader(
        settings=settings.model_copy(update={"pipeboard_api_token": SecretStr("test-token")}),
        load_tools=load,
    )
    catalog = await loader.refresh()
    assert len(catalog.read_entries()) == 8
    assert loader.current() is catalog
    search = build_discover_tools_tool(loader)
    for platform in PIPEBOARD_PLATFORMS:
        result = json.loads(search.invoke({"query": "report", "platform": platform.value}))
        assert result["tools"][0]["name"] == f"{platform.value}__get_current_report"
        entry = catalog.get(result["tools"][0]["name"])
        assert entry is not None and loader.langchain_tool(entry.qualified_name) is not None
        schema = model_facing_schema(entry, ["configured-account"])
        assert "account_alias" in schema["properties"]
        assert entry.account_arg not in schema["properties"]

    dispatcher = ReadDispatcher(
        catalog_provider=loader,
        accounts=AccountRegistry(
            bindings=(
                AccountBinding(
                    alias="site",
                    platform=Platform.GOOGLE_ANALYTICS,
                    provider_account_id="123",
                    currency="USD",
                    timezone="UTC",
                ),
            )
        ),
        provider=PipeboardReadProvider(loader),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
    )
    result = await dispatcher.execute(
        "google_analytics__get_current_report", {"account_alias": "site"}
    )
    assert calls == [{"property_id": "123"}]
    assert result.artifact_kind == "provider_result", "GA4 sessions are not ad-spend rows"
    with pytest.raises(ReadDenied, match="raw_account_id_rejected"):
        await dispatcher.execute(
            "google_analytics__get_current_report",
            {"account_alias": "site", "property_id": "other"},
        )
    assert len(calls) == 1


async def test_unavailable_connector_does_not_block_other_catalogs(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    platforms = _platform_by_url(settings)

    async def load(url: str, _headers: Any) -> list[BaseTool]:
        server_name = platforms[url]
        if server_name == "pinterest_ads":
            await asyncio.Event().wait()
        policy = DEFAULT_LOCAL_POLICY.platform_policy(Platform(server_name))
        assert policy is not None
        return [
            StructuredTool(
                name="get_report",
                description="Report",
                args_schema={
                    "type": "object",
                    "properties": {
                        policy.account_arg_names[0]: {"type": "string"},
                    },
                },
                metadata=READ_ONLY,
                func=lambda **_kwargs: "{}",
            )
        ]

    monkeypatch.setattr("paid_media_agent.tools.pipeboard.CATALOG_LOAD_TIMEOUT_SECONDS", 0.02)
    loader = PipeboardCatalogLoader(
        settings=settings.model_copy(update={"pipeboard_api_token": SecretStr("test-token")}),
        load_tools=load,
    )
    catalog = await asyncio.wait_for(loader.refresh(), timeout=1)
    assert {e.platform for e in catalog.read_entries()} == set(PIPEBOARD_PLATFORMS) - {
        Platform.PINTEREST_ADS
    }


async def test_a_real_mcp_server_reaches_the_catalog_with_its_annotations() -> None:
    """Through `langchain.mcp` and FastMCP, the way Pipeboard is loaded, over an in-memory server."""
    from fastmcp import Client, FastMCP
    from mcp.types import ToolAnnotations

    server = FastMCP("fake-pipeboard")

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_campaign_performance(customer_id: str) -> dict[str, Any]:
        """Campaign performance rows."""
        return {"rows": [{"customer_id": customer_id, "spend": 12.5}]}

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False))
    def update_campaign_budget(customer_id: str, amount: float) -> dict[str, Any]:
        """Change a budget."""
        return {"ok": True, "customer_id": customer_id, "amount": amount}

    @server.tool
    def mystery(customer_id: str) -> str:
        """No annotations at all."""
        return customer_id

    @server.tool(annotations=ToolAnnotations(read_only_hint=True))
    def get_broken(customer_id: str) -> str:
        """Always fails."""
        raise ValueError(f"no data for {customer_id}")

    tools = {t.name: t for t in await tools_from_client(Client(server))}
    raw = {
        r.name: r for r in raw_tools_from_langchain("google_ads", "mem://", list(tools.values()))
    }
    assert raw["get_campaign_performance"].annotations == {"readOnlyHint": True}
    assert raw["update_campaign_budget"].annotations == {
        "readOnlyHint": False,
        "destructiveHint": False,
    }
    assert raw["mystery"].annotations is None, "an unannotated tool is never assumed read-only"
    assert raw["get_campaign_performance"].input_schema["required"] == ["customer_id"]

    payload = await invoke_mcp_tool(
        tools["get_campaign_performance"], {"customer_id": "123"}, timeout=5
    )
    assert payload == {"rows": [{"customer_id": "123", "spend": 12.5}]}
    with pytest.raises(ProviderError, match="no data"):
        await invoke_mcp_tool(tools["get_broken"], {"customer_id": "9"}, timeout=5)
