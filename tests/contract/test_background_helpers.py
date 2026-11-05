"""Background helpers: MDA async subagents that are read-only by construction, not by prompt."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from paid_media_agent.assembly import build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.middleware.authorization import InvocationGuardMiddleware
from paid_media_agent.middleware.redaction import RedactionMiddleware
from paid_media_agent.runtime.profiles import fixture_profile
from paid_media_agent.subagents import ASYNC_TASK_TOOLS, HELPER_NAMES
from paid_media_agent.testing.scripted_model import ScriptedChatModel, Step, tool_call_message
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.check_ins import CHECK_IN_TOOLS
from paid_media_agent.tools.fixtures import build_fixture_catalog
from paid_media_agent.tools.writes import (
    DISCOVER_WRITE_OPERATIONS_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
    PROPOSE_CHANGE_TOOL,
)
from tests.contract.helpers import config

WRITE_TOOLS = {
    PROPOSE_CHANGE_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
    DISCOVER_WRITE_OPERATIONS_TOOL,
}


def _components(settings: Settings, project_root: Path, steps: list[Step], *, managed: bool) -> Any:
    catalog = build_fixture_catalog()
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=StaticCatalogProvider(catalog),
        workspace_root=settings.paid_media_workspace_root,
    )
    return build_agent_components(
        settings=settings,
        runtime=profile,
        catalog=catalog,
        model=ScriptedChatModel(steps=steps),
        managed=managed,
    )


def _guard(middleware: list[Any]) -> InvocationGuardMiddleware:
    return next(m for m in middleware if isinstance(m, InvocationGuardMiddleware))


def test_only_managed_builds_get_helpers_check_ins_and_async_task_tools(
    settings: Settings, project_root: Path
) -> None:
    local = _components(settings, project_root, [], managed=False)
    assert local.helpers == {}
    assert not set(CHECK_IN_TOOLS) & {t.name for t in local.tools}
    assert not any(_guard(list(local.middleware))._surface.allows(n) for n in ASYNC_TASK_TOOLS)

    managed = _components(settings, project_root, [], managed=True)
    assert set(managed.helpers) == set(HELPER_NAMES)
    assert set(CHECK_IN_TOOLS) <= {t.name for t in managed.tools}
    lead = _guard(list(managed.middleware))._surface
    assert all(lead.allows(n) for n in ASYNC_TASK_TOOLS)
    assert not lead.allows("task"), "the blocking subagent tier stays hidden"


def test_every_helper_is_read_only_with_its_own_guard_stack(
    settings: Settings, project_root: Path
) -> None:
    managed = _components(settings, project_root, [], managed=True)
    for name, spec in managed.helpers.items():
        names = {t.name for t in spec["tools"]}
        assert not names & WRITE_TOOLS, name
        assert not names & set(CHECK_IN_TOOLS), name
        assert "list_accounts" in names and "google_ads__get_campaign_performance" in names
        surface = _guard(spec["middleware"])._surface
        for blocked in (*WRITE_TOOLS, *ASYNC_TASK_TOOLS, *CHECK_IN_TOOLS, "write_file", "task"):
            assert not surface.allows(blocked), (name, blocked)
        assert any(isinstance(m, RedactionMiddleware) for m in spec["middleware"])
        assert spec["skills"] == ["/skills/"]
    assert "render_report" not in {t.name for t in managed.helpers["account-puller"]["tools"]}
    assert "render_report" in {t.name for t in managed.helpers["report-builder"]["tools"]}


async def test_a_helper_graph_reads_and_cannot_reach_a_write(
    settings: Settings, project_root: Path
) -> None:
    steps: list[Step] = [
        lambda _m: tool_call_message(
            PROPOSE_CHANGE_TOOL,
            {
                "account_alias": "demo-google",
                "tool_name": "google_ads__update_campaign_budget",
                "target_ref": "g-103",
                "changes": {"daily_budget": 1},
                "reason": "x",
            },
        ),
        lambda _m: tool_call_message(
            "google_ads__get_campaign_performance",
            {"account_alias": "demo-google", "start_date": "2026-08-01", "end_date": "2026-08-14"},
        ),
        lambda _m: AIMessage(content="Pulled demo-google."),
    ]
    managed = _components(settings, project_root, steps, managed=True)
    spec = managed.helpers["account-puller"]
    # Compiled the way MDA compiles an async subagent: its own tools, prompt and middleware.
    graph = create_deep_agent(
        managed.model,
        spec["tools"],
        system_prompt=spec["system_prompt"],
        middleware=spec["middleware"],
        backend=FilesystemBackend(root_dir=project_root, virtual_mode=True),
    )
    state = await graph.ainvoke({"messages": [HumanMessage("Pull demo-google")]}, config("helper"))
    results = [m for m in state["messages"] if isinstance(m, ToolMessage)]
    denied = json.loads(str(results[0].content))
    assert denied["denied"] is True and results[0].status == "error"
    assert results[1].status != "error" and "read_result" in str(results[1].content)
    assert not managed.proposal_service.proposals.list_for_thread("helper")


def test_agent_py_declares_each_helper_as_a_literal_async_subagent(project_root: Path) -> None:
    """`mda build` reads `name` and `"async"` without running code, so both must be literals that
    come after the spread."""
    tree = ast.parse((project_root / "agent.py").read_text())
    call = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "define_deep_agent"
    )
    subagents = next(kw.value for kw in call.keywords if kw.arg == "subagents")
    assert isinstance(subagents, ast.List)
    declared = []
    for entry in subagents.elts:
        assert isinstance(entry, ast.Dict)
        assert entry.keys[0] is None, "the spec spread comes first"
        literal = {
            key.value: value.value
            for key, value in zip(entry.keys[1:], entry.values[1:], strict=True)
            if isinstance(key, ast.Constant) and isinstance(value, ast.Constant)
        }
        assert literal["async"] is True
        declared.append(literal["name"])
    assert sorted(declared) == sorted(HELPER_NAMES)
