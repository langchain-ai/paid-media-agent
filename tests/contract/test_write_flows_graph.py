"""Governed writes through the real graph: happy path and every rejection the spec names."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from paid_media_agent.config import Settings
from paid_media_agent.domain.proposals import ProposalState
from paid_media_agent.tools.catalog import RawTool, build_authorized_catalog
from paid_media_agent.tools.fixtures import (
    FIXTURE_LOCAL_POLICY,
    FakeWriteProvider,
    FixtureState,
    fixture_raw_tools,
)
from paid_media_agent.tools.writes import ApprovalPolicy, WriteDenied
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


def _receipt_text(state: dict) -> str:  # type: ignore[type-arg]
    return str(state["messages"][-1].content)


def _last_tool(state: dict) -> dict:  # type: ignore[type-arg]
    return json.loads(
        next(m for m in reversed(state["messages"]) if isinstance(m, ToolMessage)).content
    )


async def test_happy_path_interrupts_then_verifies(settings: Settings, project_root: Path) -> None:
    state = FixtureState()
    provider = FakeWriteProvider(state)
    runtime, _ = build_runtime(
        settings, project_root, WRITE_STEPS, fixture_state=state, write_provider=provider
    )
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    snapshot = runtime.graph.get_state(cfg)
    assert snapshot.interrupts, "execute_change must pause for human review"
    request = snapshot.interrupts[0].value
    assert request["action_requests"][0]["name"] == "execute_change"
    assert request["review_configs"][0]["allowed_decisions"] == ["approve", "reject"]
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    assert record.state is ProposalState.AWAITING_APPROVAL
    assert record.changeset.before[0].value == 300.0 and record.changeset.after[0].value == 240
    assert provider.mutation_calls == [], "nothing executes before approval"
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    final = await resume(runtime, cfg)
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "verified" and receipt["mutation_attempted"] is True
    assert (
        len(provider.mutation_calls) == 1 and provider.mutation_calls[0][1]["daily_budget"] == 240
    )
    assert state.campaign(record.changeset.platform, "g-103")["daily_budget"] == 240.0
    assert service.get(record.changeset.proposal_id).state is ProposalState.VERIFIED  # type: ignore[union-attr]
    assert "verified" in _receipt_text(final)


async def test_approve_without_claim_is_rejected(settings: Settings, project_root: Path) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    final = await resume(runtime, cfg)  # nobody created a claim
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "rejected" and "no valid approval claim" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_tampered_persisted_proposal_is_rejected(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    tampered_args = {**record.changeset.canonical_args, "daily_budget": 9999}
    service.proposals.save(
        record.model_copy(
            update={
                "changeset": record.changeset.model_copy(update={"canonical_args": tampered_args})
            }
        )
    )
    final = await resume(runtime, cfg)
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "rejected" and "digest_mismatch" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_edit_invalidates_earlier_approval(settings: Settings, project_root: Path) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    revised = service.revise(
        record.changeset.proposal_id, editor_ref="reviewer-1", changes={"daily_budget": 250}
    )
    assert (
        revised.changeset.revision == 2
        and revised.changeset.payload_digest != record.changeset.payload_digest
    )
    assert revised.routing_id != record.routing_id
    final = await resume(runtime, cfg)
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "rejected" and "no valid approval claim" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_expired_claim_is_rejected(settings: Settings, project_root: Path) -> None:
    provider = FakeWriteProvider(FixtureState())
    policy = ApprovalPolicy(approver_refs=frozenset({"reviewer-1"}), ttl_seconds=60)
    runtime, _ = build_runtime(
        settings, project_root, WRITE_STEPS, write_provider=provider, approval_policy=policy
    )
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    runtime.components.write_executor._clock = lambda: datetime.now(UTC) + timedelta(seconds=120)  # noqa: SLF001
    final = await resume(runtime, cfg)
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "rejected" and "approval_expired" in receipt["reason"]
    assert provider.mutation_calls == []


async def test_replayed_claim_cannot_execute_twice(settings: Settings, project_root: Path) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    claim = service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    await resume(runtime, cfg)
    assert len(provider.mutation_calls) == 1
    assert runtime.profile.approvals.mark_used(claim.claim_id) is False
    try:
        await runtime.components.write_executor.execute(record.changeset.proposal_id)
    except WriteDenied:
        pass
    receipt = runtime.profile.receipts.get(record.changeset.proposal_id)
    assert receipt is not None and receipt.status in ("verified", "rejected")
    assert len(provider.mutation_calls) == 1, "a replay must never produce a second mutation"


async def test_foreign_user_and_self_approval_are_refused(
    settings: Settings, project_root: Path
) -> None:
    policy = ApprovalPolicy(approver_refs=frozenset({"reviewer-1"}), allow_self_approval=False)
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, approval_policy=policy)
    cfg = config(caller="reviewer-1")
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    for approver in ("stranger", "reviewer-1"):
        try:
            service.approve(record.changeset.proposal_id, approver_ref=approver)
        except WriteDenied as exc:
            assert exc.reason == "approver_policy"
        else:
            raise AssertionError(f"{approver} must not be able to approve")


async def test_foreign_account_and_bad_target_cannot_be_proposed(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    steps = [
        propose_step(account_alias="demo-meta"),  # google tool with a meta alias
        propose_step(target_ref="m-201"),  # target from another account
        propose_step(changes={"daily_budget": 240, "status": "PAUSED"}),  # field outside policy
        propose_step(tool_name="google_ads__delete_campaign"),
        lambda _m: AIMessage(content="end"),
    ]
    runtime, _ = build_runtime(settings, project_root, steps, write_provider=provider)
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "go"}]}, config=config()
    )
    reasons = [
        json.loads(m.content)["reason"] for m in state["messages"] if isinstance(m, ToolMessage)
    ]
    assert reasons == [
        "platform_scope",
        "target_not_readable",
        "field_not_editable",
        "not_an_admitted_mutation",
    ]
    assert runtime.components.proposal_service.proposals.list_for_thread("t-1") == []


async def test_stale_catalog_at_execution_is_rejected(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    changed = []
    for raw in fixture_raw_tools():
        if raw.platform == "google_ads" and raw.name == "update_campaign_budget":
            schema = json.loads(json.dumps(raw.input_schema))
            schema["properties"]["daily_budget"] = {"type": "string"}
            raw = RawTool(**{**raw.model_dump(), "input_schema": schema})
        changed.append(raw)
    runtime.profile.catalog_provider.replace(
        build_authorized_catalog(changed, policy=FIXTURE_LOCAL_POLICY, source="fixture")
    )  # type: ignore[attr-defined]
    final = await resume(runtime, cfg)
    receipt = _last_tool(final)["receipt"]
    assert receipt["status"] == "rejected" and "stale_catalog" in receipt["reason"]
    assert provider.mutation_calls == []


async def _run_with_behavior(
    settings: Settings, project_root: Path, behavior: str, *, readback_failures: int = 0
) -> tuple[dict, FakeWriteProvider]:  # type: ignore[type-arg]
    state = FixtureState()
    provider = FakeWriteProvider(state, behavior=behavior)  # type: ignore[arg-type]
    runtime, _ = build_runtime(
        settings, project_root, WRITE_STEPS, fixture_state=state, write_provider=provider
    )
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.approve(record.changeset.proposal_id, approver_ref="reviewer-1")
    if readback_failures:
        reads = runtime.profile.read_provider
        reads.fail_reads["google_ads__get_campaign"] = readback_failures  # type: ignore[attr-defined]
    final = await resume(runtime, cfg)
    return _last_tool(final)["receipt"], provider


async def test_timeout_after_commit_is_verified_by_readback_without_retry(
    settings: Settings, project_root: Path
) -> None:
    receipt, provider = await _run_with_behavior(settings, project_root, "timeout_after_commit")
    assert receipt["status"] == "verified" and "timed out" in receipt["reason"]
    assert len(provider.mutation_calls) == 1


async def test_timeout_without_commit_is_failed_not_retried(
    settings: Settings, project_root: Path
) -> None:
    receipt, provider = await _run_with_behavior(settings, project_root, "timeout_without_commit")
    assert receipt["status"] == "failed" and "before value" in receipt["reason"]
    assert len(provider.mutation_calls) == 1


async def test_provider_error_is_failed(settings: Settings, project_root: Path) -> None:
    receipt, provider = await _run_with_behavior(settings, project_root, "error")
    assert receipt["status"] == "failed" and len(provider.mutation_calls) == 1


async def test_unprovable_readback_is_unknown(settings: Settings, project_root: Path) -> None:
    receipt, provider = await _run_with_behavior(
        settings, project_root, "timeout_after_commit", readback_failures=10
    )
    assert receipt["status"] == "unknown" and receipt["readback_attempts"] == 3, "bounded readback"
    assert len(provider.mutation_calls) == 1


async def test_process_recovery_resumes_from_checkpoint_with_new_graph(
    settings: Settings, project_root: Path
) -> None:
    state = FixtureState()
    provider = FakeWriteProvider(state)
    checkpointer = InMemorySaver()
    from paid_media_agent.runtime.profiles import fixture_profile
    from paid_media_agent.tools.catalog import StaticCatalogProvider
    from paid_media_agent.tools.fixtures import build_fixture_catalog

    catalog = build_fixture_catalog()
    catalog_provider = StaticCatalogProvider(catalog)
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=catalog_provider,
        workspace_root=settings.paid_media_workspace_root,
        fixture_state=state,
        write_provider=provider,
    )
    runtime, _ = build_runtime(
        settings,
        project_root,
        WRITE_STEPS,
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
        checkpointer=checkpointer,
    )
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    record = runtime.components.proposal_service.proposals.list_for_thread("t-1")[0]
    # "Restart": a brand-new graph and model over the same checkpointer and persisted repositories.
    restarted, _ = build_runtime(
        settings,
        project_root,
        [final_step],  # the only remaining model call after the tool result
        catalog=catalog,
        catalog_provider=catalog_provider,
        profile=profile,
        checkpointer=checkpointer,
    )
    assert restarted.graph.get_state(cfg).interrupts
    restarted.components.proposal_service.approve(
        record.changeset.proposal_id, approver_ref="reviewer-1"
    )
    final = await resume(restarted, cfg)
    assert _last_tool(final)["receipt"]["status"] == "verified"
    assert len(provider.mutation_calls) == 1


async def test_reject_decision_leaves_provider_untouched(
    settings: Settings, project_root: Path
) -> None:
    provider = FakeWriteProvider(FixtureState())
    runtime, _ = build_runtime(settings, project_root, WRITE_STEPS, write_provider=provider)
    cfg = config()
    await run_until_interrupt(runtime, cfg)
    service = runtime.components.proposal_service
    record = service.proposals.list_for_thread("t-1")[0]
    service.reject(record.changeset.proposal_id, actor_ref="reviewer-1", message="not now")
    final = await resume(runtime, cfg, decision="reject")
    tool_message = next(m for m in reversed(final["messages"]) if isinstance(m, ToolMessage))
    assert tool_message.status == "error" and "rejected" in tool_message.content
    assert service.get(record.changeset.proposal_id).state is ProposalState.REJECTED  # type: ignore[union-attr]
    assert provider.mutation_calls == []
