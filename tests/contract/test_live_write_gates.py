"""The live write path is unreachable without every operator gate, and fakes stay honest."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.proposals import ProposalState
from paid_media_agent.runtime.profiles import fixture_profile
from paid_media_agent.testing.scripted_model import tool_call_message
from paid_media_agent.tools.catalog import CatalogEntry, StaticCatalogProvider
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.write_policy import WriteOperation, WritePolicy
from tests.contract.helpers import (
    build_runtime,
    config,
    execute_step,
    final_step,
    propose_step,
    resume,
    run_until_interrupt,
)

WRITE_STEPS = [propose_step(), execute_step, final_step]


def _last_tool(state: dict) -> dict:  # type: ignore[type-arg]
    return json.loads(
        next(m for m in reversed(state["messages"]) if isinstance(m, ToolMessage)).content
    )


class LiveLikeProvider:
    """A provider that is *not* marked fake. It records calls and never mutates anything."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []

    async def call_mutation(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.calls.append((entry.qualified_name, dict(arguments)))
        return {"operation_ref": "should-never-happen"}


def _live_profile(settings: Settings, project_root: Path, provider: LiveLikeProvider):  # type: ignore[no-untyped-def]
    catalog = build_fixture_catalog()
    catalog_provider = StaticCatalogProvider(catalog)
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=catalog_provider,
        workspace_root=settings.paid_media_workspace_root,
    )
    return (
        catalog,
        catalog_provider,
        replace(profile, write_provider=provider, write_provider_is_fake=False),
    )


async def _stage_and_approve(runtime, cfg):  # type: ignore[no-untyped-def]
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    return record


async def test_live_provider_is_refused_without_every_gate(
    settings: Settings, project_root: Path
) -> None:
    provider = LiveLikeProvider()
    catalog, catalog_provider, profile = _live_profile(settings, project_root, provider)
    runtime, _ = build_runtime(
        settings,
        project_root,
        WRITE_STEPS,
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
    )
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "writes_disabled" in receipt["reason"]
    assert provider.calls == []
    assert "live provider; writes disabled" in runtime.components.metadata.write_gate


async def test_live_provider_needs_pinned_revision_and_released_tool(
    settings: Settings, project_root: Path
) -> None:
    provider = LiveLikeProvider()
    enabled = settings.model_copy(update={"paid_media_writes_enabled": True})
    catalog, catalog_provider, profile = _live_profile(enabled, project_root, provider)
    runtime, _ = build_runtime(
        enabled,
        project_root,
        WRITE_STEPS,
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
    )
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "live_writes_not_released" in receipt["reason"]

    pinned = enabled.model_copy(
        update={
            "paid_media_live_write_catalog_revision": "some-other-revision",
            "paid_media_live_write_canary_tools": "google_ads__update_campaign_budget",
        }
    )
    catalog, catalog_provider, profile = _live_profile(pinned, project_root, provider)
    runtime, _ = build_runtime(
        pinned,
        project_root,
        WRITE_STEPS,
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
    )
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "stale_catalog" in receipt["reason"]

    unreleased = enabled.model_copy(
        update={
            "paid_media_live_write_catalog_revision": catalog.revision,
            "paid_media_live_write_canary_tools": "google_ads__update_campaign_status",
        }
    )
    catalog, catalog_provider, profile = _live_profile(unreleased, project_root, provider)
    runtime, _ = build_runtime(
        unreleased,
        project_root,
        WRITE_STEPS,
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
    )
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "tool_not_released" in receipt["reason"]
    assert provider.calls == [], "no gate combination in tests reaches the provider"


async def test_kill_switch_halts_even_fake_execution(
    settings: Settings, project_root: Path, tmp_path: Path
) -> None:
    switch = tmp_path / "KILL_SWITCH"
    halted = settings.model_copy(update={"paid_media_kill_switch_path": switch})
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(halted, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    switch.write_text("incident in progress")
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "kill_switch" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_policy_change_after_proposal_is_rejected(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    record = await _stage_and_approve(runtime, cfg)
    executor = runtime.components.write_executor
    current = executor._write_policy.get(record.changeset.tool_name)
    assert current is not None
    altered = WriteOperation(
        **{
            **current.model_dump(),
            "readback_fields": {"daily_budget": "daily_budget"},
            "units": {"daily_budget": "changed"},
        }
    )
    executor._write_policy = WritePolicy(
        operations=tuple(
            altered if op.tool_name == altered.tool_name else op
            for op in executor._write_policy.operations
        )
    )
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "rejected" and "stale_policy" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_unknown_proposal_id_does_not_interrupt(
    settings: Settings, project_root: Path
) -> None:
    steps = [
        lambda _m: tool_call_message(
            "execute_change", {"proposal_id": "00000000-0000-0000-0000-000000000009"}
        ),
        lambda _m: tool_call_message("execute_change", {"proposal_id": "not-a-uuid"}),
        lambda _m: AIMessage(content="end"),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    cfg = config()
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "go"}]}, config=cfg
    )
    assert not runtime.graph.get_state(cfg).interrupts, "bogus ids never reach a reviewer"
    bodies = [json.loads(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]
    assert bodies[0]["denied"] and bodies[0]["reason"] == "unknown_proposal"
    assert bodies[1]["reason"] == "invalid_proposal_id"


async def test_foreign_thread_proposal_does_not_interrupt(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(
        settings, project_root, [propose_step(), final_step], write_provider=provider
    )
    await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "stage"}]}, config=config(thread_id="owner")
    )
    record = runtime.components.proposal_service.proposals.list_for_thread("owner")[0]
    pid = str(record.changeset.proposal_id)
    hijack, _ = build_runtime(
        settings,
        project_root,
        [lambda _m: tool_call_message("execute_change", {"proposal_id": pid}), final_step],
        profile=runtime.profile,
        catalog=runtime.catalog,
        catalog_provider=runtime.profile.catalog_provider,
    )  # type: ignore[arg-type]
    cfg = config(thread_id="intruder", caller="someone-else")
    state = await hijack.graph.ainvoke(
        {"messages": [{"role": "user", "content": "execute it"}]}, config=cfg
    )
    assert not hijack.graph.get_state(cfg).interrupts
    assert _last_tool(state)["receipt"]["status"] == "rejected"
    assert provider.mutation_calls == []
    assert (
        runtime.components.proposal_service.get(record.changeset.proposal_id).state
        is not ProposalState.VERIFIED
    )  # type: ignore[union-attr]


async def test_validate_only_runs_before_the_single_mutation(
    settings: Settings, project_root: Path
) -> None:
    state = FixtureState()
    provider = FakeWriteProvider(state)
    runtime, _ = build_runtime(
        settings, project_root, WRITE_STEPS, fixture_state=state, write_provider=provider
    )
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "verified" and receipt["provider_acknowledged"] is True
    assert (
        len(provider.validation_calls) == 1
        and provider.validation_calls[0][1]["validate_only"] is True
    )
    assert (
        len(provider.mutation_calls) == 1 and "validate_only" not in provider.mutation_calls[0][1]
    )


async def test_validation_refusal_fails_without_a_mutation_attempt(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState(), behavior="validation_error")
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "failed" and receipt["mutation_attempted"] is False
    assert receipt["provider_acknowledged"] is False and "validation" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_timeout_receipt_is_honest_about_acknowledgement(
    settings: Settings, project_root: Path
) -> None:
    state = FixtureState()
    provider = FakeWriteProvider(state, behavior="timeout_after_commit")
    runtime, _ = build_runtime(
        settings, project_root, WRITE_STEPS, fixture_state=state, write_provider=provider
    )
    cfg = config()
    await _stage_and_approve(runtime, cfg)
    receipt = _last_tool(await resume(runtime, cfg))["receipt"]
    assert receipt["status"] == "verified" and receipt["provider_acknowledged"] is False
    assert receipt["mutation_attempted"] is True


async def test_discover_write_operations_lists_only_admitted_operations(
    settings: Settings, project_root: Path
) -> None:
    steps = [lambda _m: tool_call_message("discover_write_operations", {}), final_step]
    runtime, _ = build_runtime(settings, project_root, steps)
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "what can you change?"}]}, config=config()
    )
    body = _last_tool(state)
    names = {op["tool_name"] for op in body["operations"]}
    assert names == {
        f"{p}__update_campaign_{f}"
        for p in ("google_ads", "meta_ads", "reddit_ads")
        for f in ("budget", "status")
    }
    assert all("editable_fields" in op and "risk" in op for op in body["operations"])
    assert "fake provider" in body["execution_gate"]


async def test_proposal_carries_risk_flags_and_contract_identity(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(
        settings,
        project_root,
        [propose_step(changes={"daily_budget": 900}), final_step],
        write_provider=provider,
    )
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "raise it"}]}, config=config()
    )
    proposal = _last_tool(state)["proposal"]
    assert {"budget_delta", "budget_increase"} <= set(proposal["risk_flags"])
    record = runtime.components.proposal_service.proposals.list_for_thread("t-1")[0]
    assert record.changeset.schema_hash and record.changeset.policy_digest
