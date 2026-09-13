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
from paid_media_agent.tools.pipeboard import PipeboardCatalogLoader, PipeboardReadProvider
from paid_media_agent.tools.reads import ReadDenied, ReadDispatcher, model_facing_schema


async def test_all_catalogs_load_concurrently_and_new_platforms_are_searchable(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    started: set[str] = set()
    ready = asyncio.Event()
    calls: list[dict[str, Any]] = []

    async def report(**kwargs: Any) -> str:
        calls.append(kwargs)
        return json.dumps({"rows": [{"date": "2026-08-28", "sessions": 12}]})

    class Client:
        def __init__(self, connections: dict[str, Any]) -> None:
            assert set(connections) == {p.value for p in PIPEBOARD_PLATFORMS}

        async def get_tools(self, *, server_name: str) -> list[BaseTool]:
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
                    metadata={"readOnlyHint": True},
                    coroutine=report,
                )
            ]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", Client)
    loader = PipeboardCatalogLoader(
        settings=settings.model_copy(update={"pipeboard_api_token": SecretStr("test-token")})
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
    class Client:
        def __init__(self, connections: Any) -> None:
            pass

        async def get_tools(self, *, server_name: str) -> list[BaseTool]:
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
                    metadata={"readOnlyHint": True},
                    func=lambda **_kwargs: "{}",
                )
            ]

    monkeypatch.setattr("langchain_mcp_adapters.client.MultiServerMCPClient", Client)
    monkeypatch.setattr("paid_media_agent.tools.pipeboard.CATALOG_LOAD_TIMEOUT_SECONDS", 0.02)
    loader = PipeboardCatalogLoader(
        settings=settings.model_copy(update={"pipeboard_api_token": SecretStr("test-token")})
    )
    catalog = await asyncio.wait_for(loader.refresh(), timeout=1)
    assert {e.platform for e in catalog.read_entries()} == set(PIPEBOARD_PLATFORMS) - {
        Platform.PINTEREST_ADS
    }
