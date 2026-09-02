from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from paid_media_agent.config import Settings
from paid_media_agent.testing.demo_script import DEMO_QUESTION, demo_steps
from paid_media_agent.testing.scripted_model import tool_call_message
from paid_media_agent.tools.fixtures import build_fixture_catalog
from tests.contract.helpers import build_runtime, config


async def test_fixture_demo_reconciles_and_cites_artifacts(
    settings: Settings, project_root: Path
) -> None:
    runtime, model = build_runtime(settings, project_root, demo_steps())
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": DEMO_QUESTION}]}, config=config()
    )
    answer = state["messages"][-1].content
    assert "reconciled=yes" in answer
    assert "art_" in answer and "conversion_value" in answer and "unavailable, not zero" in answer
    assert "No cross-platform total" in answer
    assert len(runtime.components.read_dispatcher.audit) == 3
    # Raw provider ids never reach the model transcript.
    transcript = json.dumps([m.model_dump() for m in state["messages"]], default=str)
    assert "fixture-google-0001" not in transcript
    assert model.bound_tool_batches, "the scripted model must have been bound with tools"
    names = {t["function"]["name"] for t in model.bound_tool_batches[-1]}
    assert "task" not in names and "execute" not in names and "delete" not in names
    assert not any(n.endswith("update_campaign_budget") or n.endswith("__mutate") for n in names)
    assert {
        "discover_tools",
        "list_accounts",
        "compare_periods",
        "render_report",
        "propose_change",
        "execute_change",
    } <= names


async def test_guard_denies_hallucinated_and_hidden_tools(
    settings: Settings, project_root: Path
) -> None:
    steps = [
        lambda _m: tool_call_message(
            "google_ads__update_campaign_budget",
            {"account_alias": "demo-google", "campaign_id": "g-101", "daily_budget": 1},
        ),
        lambda _m: tool_call_message(
            "task", {"description": "x", "subagent_type": "general-purpose"}
        ),
        lambda _m: tool_call_message(
            "google_ads__mutate", {"account_alias": "demo-google", "operations": []}
        ),
        lambda _m: AIMessage(content="stopped"),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "Do it."}]}, config=config()
    )
    tool_messages = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    assert len(tool_messages) == 3
    for message in tool_messages:
        body = json.loads(message.content)
        assert body["denied"] is True and message.status == "error"
    assert runtime.profile.write_provider.mutation_calls == []  # type: ignore[attr-defined]
    guard = next(m for m in runtime.components.middleware if m.name == "PaidMediaInvocationGuard")
    assert {reason for _, reason in guard.denials} == {"outside_tool_surface"}


async def test_stale_catalog_selection_fails_closed(settings: Settings, project_root: Path) -> None:
    from paid_media_agent.tools.catalog import RawTool, build_authorized_catalog
    from paid_media_agent.tools.fixtures import FIXTURE_LOCAL_POLICY, fixture_raw_tools

    steps = [
        lambda _m: tool_call_message(
            "google_ads__get_campaign_performance",
            {"account_alias": "demo-google", "start_date": "2026-08-01", "end_date": "2026-08-28"},
        ),
        lambda _m: AIMessage(content="end"),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    changed = []
    for raw in fixture_raw_tools():
        if raw.platform == "google_ads" and raw.name == "get_campaign_performance":
            schema = dict(raw.input_schema)
            schema["properties"] = {**schema["properties"], "segment": {"type": "string"}}
            raw = RawTool(**{**raw.model_dump(), "input_schema": schema})
        changed.append(raw)
    runtime.profile.catalog_provider.replace(
        build_authorized_catalog(changed, policy=FIXTURE_LOCAL_POLICY, source="fixture")
    )  # type: ignore[attr-defined]
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "read"}]}, config=config()
    )
    body = json.loads(next(m for m in state["messages"] if isinstance(m, ToolMessage)).content)
    assert body["denied"] and body["reason"] == "stale_selection"


def test_fixture_catalog_never_binds_mutations_to_model_tools(
    settings: Settings, project_root: Path
) -> None:
    runtime, _ = build_runtime(settings, project_root, [lambda _m: AIMessage(content="x")])
    bound = {t.name for t in runtime.components.tools}
    mutation_names = {e.qualified_name for e in build_fixture_catalog().mutation_entries()}
    denied_names = {e.qualified_name for e in build_fixture_catalog().denied_entries()}
    assert not bound & mutation_names and not bound & denied_names
