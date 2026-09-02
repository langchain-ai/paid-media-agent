"""Model matrix: provider-native search vs portable selector, same authorized catalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage
from langchain_core.messages.utils import count_tokens_approximately

from paid_media_agent.config import Settings
from paid_media_agent.middleware.tool_selection import SelectionStrategy
from paid_media_agent.runtime.profiles import fixture_profile
from paid_media_agent.testing.fake_models import RecordingProviderModel
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.fixtures import build_fixture_catalog
from tests.contract.helpers import config

PLATFORM_TOOL_COUNT = 9  # 3 platforms x 3 authorized reads


def _settings(base: Settings, model_spec: str, selector: str | None = None) -> Settings:
    return base.model_copy(
        update={"paid_media_model": model_spec, "paid_media_tool_selector_model": selector}
    )


def _runtime(
    settings: Settings,
    project_root: Path,
    model: RecordingProviderModel,
    selector: RecordingProviderModel | None = None,
):  # type: ignore[no-untyped-def]
    catalog = build_fixture_catalog()
    provider = StaticCatalogProvider(catalog)
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=provider,
        workspace_root=settings.paid_media_workspace_root,
    )
    from langgraph.checkpoint.memory import InMemorySaver

    from paid_media_agent.assembly import build_agent_components
    from paid_media_agent.runtime.local import compile_graph

    components = build_agent_components(
        settings=settings, runtime=profile, catalog=catalog, model=model, selector_model=selector
    )
    graph = compile_graph(components, project_root=project_root, checkpointer=InMemorySaver())
    return components, graph


def _schema_tokens(batch: list[dict]) -> int:  # type: ignore[type-arg]
    return count_tokens_approximately([AIMessage(content=json.dumps(batch, default=str))])


@pytest.mark.parametrize(
    ("spec", "provider", "expected_strategy", "search_tool_type"),
    [
        (
            "anthropic:claude-sonnet-4-6",
            "anthropic",
            SelectionStrategy.PROVIDER_NATIVE,
            "tool_search_tool_bm25_20251119",
        ),
        ("openai:gpt-5.5", "openai", SelectionStrategy.PROVIDER_NATIVE, "tool_search"),
    ],
)
async def test_provider_native_path_defers_platform_tools(
    settings: Settings,
    project_root: Path,
    spec: str,
    provider: str,
    expected_strategy: SelectionStrategy,
    search_tool_type: str,
) -> None:
    model = RecordingProviderModel(
        provider=provider, model_name=spec.split(":")[1], responses=[AIMessage(content="ok")]
    )
    components, graph = _runtime(_settings(settings, spec), project_root, model)
    assert components.metadata.selection.strategy is expected_strategy
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Which campaigns need attention?"}]},
        config=config(),
    )
    batch = model.bound_batches[-1]
    deferred = [t for t in batch if isinstance(t, dict) and t.get("defer_loading")]
    search_tools = [t for t in batch if isinstance(t, dict) and t.get("type") == search_tool_type]
    assert len(deferred) == PLATFORM_TOOL_COUNT, "every authorized platform read is deferred"
    assert len(search_tools) == 1, "exactly one provider search tool is injected"
    named = {t["function"]["name"] for t in batch if "function" in t}
    assert {"compare_periods", "discover_tools", "list_accounts", "propose_change"} <= named
    assert not any(n.endswith("__mutate") or "delete" in n for n in named)
    assert "task" not in named and "execute" not in named
    print(
        f"{spec}: bound={len(batch)} deferred={len(deferred)} schema_tokens={_schema_tokens(batch)}"
    )


async def test_portable_selector_path_bounds_platform_tools(
    settings: Settings, project_root: Path
) -> None:
    spec = "google_genai:gemini-3-flash"
    selector = RecordingProviderModel(
        provider="google_genai",
        model_name="selector",
        responses=[AIMessage(content="")],
        structured_selection=[
            "google_ads__get_campaign_performance",
            "meta_ads__get_campaign_performance",
        ],
    )
    model = RecordingProviderModel(
        provider="google_genai", model_name="gemini-3-flash", responses=[AIMessage(content="ok")]
    )
    components, graph = _runtime(_settings(settings, spec), project_root, model, selector)
    assert components.metadata.selection.strategy is SelectionStrategy.PORTABLE_SELECTOR
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Compare campaign performance."}]},
        config=config(),
    )
    batch = model.bound_batches[-1]
    named = {t["function"]["name"] for t in batch if "function" in t}
    platform_bound = {n for n in named if "__" in n}
    assert platform_bound == {
        "google_ads__get_campaign_performance",
        "meta_ads__get_campaign_performance",
    }
    assert {
        "compare_periods",
        "discover_tools",
        "list_accounts",
        "propose_change",
        "read_file",
    } <= named
    assert not any(t.get("defer_loading") for t in batch if isinstance(t, dict))
    assert not any(t.get("type") == "tool_search" for t in batch if isinstance(t, dict))
    print(f"{spec}: bound={len(batch)} schema_tokens={_schema_tokens(batch)}")


async def test_portable_selector_hallucinated_name_cannot_reach_mutations(
    settings: Settings, project_root: Path
) -> None:
    selector = RecordingProviderModel(
        provider="google_genai",
        model_name="selector",
        responses=[AIMessage(content="")],
        structured_selection=[
            "google_ads__update_campaign_budget",
            "google_ads__mutate",
            "google_ads__list_campaigns",
        ],
    )
    model = RecordingProviderModel(
        provider="google_genai", model_name="gemini-3-flash", responses=[AIMessage(content="ok")]
    )
    _, graph = _runtime(
        _settings(settings, "google_genai:gemini-3-flash"), project_root, model, selector
    )
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": "Change budgets."}]}, config=config()
    )
    named = {t["function"]["name"] for t in model.bound_batches[-1] if "function" in t}
    assert "google_ads__update_campaign_budget" not in named and "google_ads__mutate" not in named
    # The whole hallucinated selection is discarded: only core tools remain this turn.
    assert not any("__" in n for n in named)
    assert {"discover_tools", "compare_periods", "list_accounts"} <= named


async def test_both_paths_expose_the_same_authorized_reachability(
    settings: Settings, project_root: Path
) -> None:
    native_model = RecordingProviderModel(
        provider="anthropic", model_name="claude-sonnet-4-6", responses=[AIMessage(content="ok")]
    )
    native_components, _ = _runtime(
        _settings(settings, "anthropic:claude-sonnet-4-6"), project_root, native_model
    )
    portable_model = RecordingProviderModel(
        provider="google_genai", model_name="gemini-3-flash", responses=[AIMessage(content="ok")]
    )
    portable_components, _ = _runtime(
        _settings(settings, "google_genai:gemini-3-flash"), project_root, portable_model
    )
    assert set(native_components.metadata.tool_names) == set(
        portable_components.metadata.tool_names
    )
    assert (
        native_components.metadata.catalog_revision == portable_components.metadata.catalog_revision
    )
