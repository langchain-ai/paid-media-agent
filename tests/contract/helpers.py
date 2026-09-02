"""Builders for real-graph contract tests: scripted models, local runtimes, and step helpers."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from paid_media_agent.config import Settings
from paid_media_agent.runtime.local import LocalRuntime, build_local_runtime
from paid_media_agent.runtime.profiles import RuntimeProfile, fixture_profile
from paid_media_agent.testing.demo_script import demo_steps, write_demo_steps
from paid_media_agent.testing.scripted_model import (
    ScriptedChatModel,
    Step,
    last_tool_results,
    tool_call_message,
)
from paid_media_agent.tools.catalog import AuthorizedToolCatalog, StaticCatalogProvider
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.writes import ApprovalPolicy


def config(thread_id: str = "t-1", caller: str = "local-user") -> RunnableConfig:
    return RunnableConfig(configurable={"thread_id": thread_id, "caller_ref": caller})


def propose_step(**overrides: Any) -> Step:
    args: dict[str, Any] = {
        "account_alias": "demo-google",
        "tool_name": "google_ads__update_campaign_budget",
        "target_ref": "g-103",
        "changes": {"daily_budget": 240},
        "reason": "Reduce budget after CPA rose.",
    }
    args.update(overrides)
    return lambda _messages: tool_call_message("propose_change", args)


def execute_step(messages: Sequence[BaseMessage]) -> AIMessage:
    proposal = next((r for r in last_tool_results(messages) if "proposal" in r), None)
    if proposal is None:
        return AIMessage(content=f"proposal failed: {last_tool_results(messages)}")
    return tool_call_message("execute_change", {"proposal_id": proposal["proposal"]["proposal_id"]})


def final_step(messages: Sequence[BaseMessage]) -> AIMessage:
    results = last_tool_results(messages)
    return AIMessage(content=f"done: {results[-1] if results else 'no results'}")


def build_runtime(
    settings: Settings,
    project_root: Path,
    steps: list[Step],
    *,
    catalog: AuthorizedToolCatalog | None = None,
    catalog_provider: StaticCatalogProvider | None = None,
    fixture_state: FixtureState | None = None,
    write_provider: FakeWriteProvider | None = None,
    approval_policy: ApprovalPolicy | None = None,
    profile: RuntimeProfile | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> tuple[LocalRuntime, ScriptedChatModel]:
    model = ScriptedChatModel(steps=steps)
    resolved_catalog = catalog or build_fixture_catalog()
    provider = catalog_provider or StaticCatalogProvider(resolved_catalog)
    state = fixture_state or FixtureState()
    resolved_profile = profile or fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=provider,
        workspace_root=settings.paid_media_workspace_root,
        fixture_state=state,
        write_provider=write_provider,
        approval_policy=approval_policy,
    )
    runtime = build_local_runtime(
        settings,
        project_root=project_root,
        model=model,
        catalog=resolved_catalog,
        catalog_provider=provider,
        profile=resolved_profile,
        checkpointer=checkpointer,
    )
    return runtime, model


async def run_until_interrupt(
    runtime: LocalRuntime, cfg: RunnableConfig, text: str = "Change the budget."
) -> dict[str, Any]:
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": text}]}, config=cfg
    )
    return dict(state)


async def resume(
    runtime: LocalRuntime, cfg: RunnableConfig, decision: str = "approve"
) -> dict[str, Any]:
    state = await runtime.graph.ainvoke(
        Command(resume={"decisions": [{"type": decision}]}), config=cfg
    )
    return dict(state)


__all__ = ["demo_steps", "write_demo_steps"]
