"""Surface parity: the Block Kit service and the MDA definition drive the same components."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paid_media_agent.config import Settings
from paid_media_agent.persistence.memory import InMemoryDedupeStore, InMemoryThreadOwnershipStore
from paid_media_agent.surfaces.runner import AgentRunner
from paid_media_agent.surfaces.slack.blocks import ACTION_APPROVE
from paid_media_agent.surfaces.slack.service import (
    SlackApplicationService,
    slack_caller_ref,
    slack_thread_id,
)
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureState
from paid_media_agent.tools.writes import ApprovalPolicy
from tests.contract.helpers import build_runtime, execute_step, final_step, propose_step

WRITE_STEPS = [propose_step(), execute_step, final_step]


def _slack_event(team: str, channel: str, ts: str, user: str, text: str, event_id: str) -> dict:  # type: ignore[type-arg]
    return {
        "type": "event_callback",
        "event_id": event_id,
        "team_id": team,
        "event": {"type": "app_mention", "channel": channel, "ts": ts, "user": user, "text": text},
    }


async def test_slack_review_and_button_approval_resume_the_same_graph(
    settings: Settings, project_root: Path
) -> None:
    state = FixtureState()
    provider = FakeWriteProvider(state)
    reviewer = slack_caller_ref("T1", "U-reviewer")
    policy = ApprovalPolicy(
        approver_refs=frozenset({reviewer, "api-reviewer"}), allow_self_approval=False
    )
    runtime, _ = build_runtime(
        settings,
        project_root,
        WRITE_STEPS,
        fixture_state=state,
        write_provider=provider,
        approval_policy=policy,
    )
    threads = InMemoryThreadOwnershipStore()
    runner = AgentRunner(
        graph=runtime.graph,
        service=runtime.components.proposal_service,
        receipts=runtime.profile.receipts,
        threads=threads,
    )
    slack = SlackApplicationService(runner=runner, dedupe=InMemoryDedupeStore())

    reply = await slack.handle_event(
        _slack_event("T1", "C1", "1.0", "U-requester", "<@BOT> lower the PMax budget", "Ev1")
    )
    assert reply is not None and reply.outcome is not None and reply.outcome.interrupted
    actions = next(b for b in reply.message.blocks if b["type"] == "actions")
    routing_id = next(e["value"] for e in actions["elements"] if e["action_id"] == ACTION_APPROVE)
    assert routing_id == reply.outcome.proposal.routing_id  # type: ignore[union-attr]
    assert (
        await slack.handle_event(_slack_event("T1", "C1", "1.0", "U-requester", "again", "Ev1"))
        is None
    ), "duplicate events are dropped"

    # The routing id resolves to the persisted proposal; the requester is the Slack caller.
    proposal = runner.proposal_by_routing_id(routing_id)
    assert proposal is not None
    thread_id = slack_thread_id("T1", "C1", "1.0")
    assert proposal.requester_ref == slack_caller_ref("T1", "U-requester")
    assert proposal.requester_ref != reviewer

    # Requester cannot approve their own proposal; the reviewer can, through a Slack button.
    own = await slack.handle_action(
        {
            "actions": [{"action_id": ACTION_APPROVE, "value": routing_id}],
            "team": {"id": "T1"},
            "user": {"id": "U-requester"},
            "channel": {"id": "C1"},
            "message": {"ts": "1.0"},
            "trigger_id": "tr1",
        }
    )
    assert own is not None and "refused" in own.message.text and provider.mutation_calls == []
    approved = await slack.handle_action(
        {
            "actions": [{"action_id": ACTION_APPROVE, "value": routing_id}],
            "team": {"id": "T1"},
            "user": {"id": "U-reviewer"},
            "channel": {"id": "C1"},
            "message": {"ts": "1.0"},
            "trigger_id": "tr2",
        }
    )
    assert approved is not None and approved.outcome is not None
    assert approved.outcome.receipt is not None and approved.outcome.receipt.status == "verified"
    assert "Change verified" in json.dumps(list(approved.message.blocks))
    assert len(provider.mutation_calls) == 1
    assert runner.receipt(proposal.proposal_id) is not None
    assert threads.owner(thread_id) == slack_caller_ref("T1", "U-requester")


def test_mda_definition_uses_shared_components(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib
    import sys

    monkeypatch.delenv("PIPEBOARD_API_TOKEN", raising=False)
    # The import reads the developer's .env; pin the model so a local typo cannot fail the suite.
    monkeypatch.setenv("PAID_MEDIA_MODEL", "anthropic:claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    monkeypatch.chdir(project_root)
    sys.modules.pop("agent", None)
    module = importlib.import_module("agent")
    definition = module.agent
    config = definition.config
    assert config["name"] == "paid-media-agent"
    names = {t.name for t in config["tools"]}
    assert {"discover_tools", "compare_periods", "propose_change", "execute_change"} <= names
    assert not any(n.endswith("__mutate") or "delete" in n for n in names)
    assert "execute_change" in config["interrupt_on"]
    middleware_names = {m.name for m in config["middleware"]}
    assert {
        "PaidMediaInvocationGuard",
        "PaidMediaRedaction",
        "PaidMediaResultOffload",
    } <= middleware_names
    assert (project_root / "channels" / "slack.py").exists()


def test_configured_runtime_compiles_the_deployment_profile_locally(
    settings: Settings, project_root: Path
) -> None:
    from paid_media_agent.runtime.local import build_configured_runtime
    from paid_media_agent.testing.scripted_model import ScriptedChatModel

    runtime = build_configured_runtime(
        settings, project_root=project_root, model=ScriptedChatModel(steps=[])
    )
    assert runtime.profile.name == "mda"
    assert runtime.components.metadata.catalog_source == "fixture"
    assert runtime.profile.write_provider_is_fake is True, "no live adapter without credentials"
    assert {t.name for t in runtime.components.tools} >= {
        "discover_tools",
        "compare_periods",
        "render_report",
        "get_org_context",
    }
