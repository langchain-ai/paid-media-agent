"""Surface parity: Slack, the API, the MDA definition, and the self-hosted runtime share one assembly."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from paid_media_agent.config import Settings
from paid_media_agent.persistence.memory import InMemoryDedupeStore, InMemoryThreadOwnershipStore
from paid_media_agent.surfaces.api.app import create_app
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

    events = []

    async def observe(event):
        events.append(event)

    reply = await slack.handle_event(
        _slack_event("T1", "C1", "1.0", "U-requester", "<@BOT> lower the PMax budget", "Ev1"),
        on_event=observe,
    )
    assert reply is not None and reply.outcome is not None and reply.outcome.interrupted
    assert events[0].kind == "start"
    assert any(event.kind == "tool" and event.status == "in_progress" for event in events)
    assert any(event.kind == "tool" and event.status == "complete" for event in events)
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
        },
        on_event=observe,
    )
    assert approved is not None and approved.outcome is not None
    assert approved.outcome.receipt is not None and approved.outcome.receipt.status == "verified"
    assert approved.message.text and not approved.message.blocks
    assert "".join(event.text for event in events if event.kind == "text") == approved.message.text
    assert len(provider.mutation_calls) == 1
    assert runner.receipt(proposal.proposal_id) is not None
    assert threads.owner(thread_id) == slack_caller_ref("T1", "U-requester")


async def test_api_and_slack_share_persisted_state(settings: Settings, project_root: Path) -> None:
    fastapi = pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    state = FixtureState()
    provider = FakeWriteProvider(state)
    policy = ApprovalPolicy(approver_refs=frozenset({"api-reviewer"}), allow_self_approval=False)
    api_settings = settings.model_copy(
        update={
            "paid_media_api_tokens": __import__("pydantic").SecretStr(
                "tok-req:api-requester,tok-rev:api-reviewer"
            )
        }
    )
    runtime, _ = build_runtime(
        api_settings,
        project_root,
        WRITE_STEPS,
        fixture_state=state,
        write_provider=provider,
        approval_policy=policy,
    )

    class Holder:
        pass

    holder = Holder()
    holder.settings = api_settings  # type: ignore[attr-defined]
    holder.graph = runtime.graph  # type: ignore[attr-defined]
    holder.components = runtime.components  # type: ignore[attr-defined]
    holder.profile = runtime.profile  # type: ignore[attr-defined]
    holder.catalog = runtime.catalog  # type: ignore[attr-defined]
    holder.threads = InMemoryThreadOwnershipStore()  # type: ignore[attr-defined]
    holder.persistence = "memory"  # type: ignore[attr-defined]
    app = create_app(holder)
    client = TestClient(app)
    assert client.get("/health").json()["writes_enabled"] is False
    assert client.post("/threads/api-1/messages", json={"text": "lower budget"}).status_code == 401
    requester = {"Authorization": "Bearer tok-req"}
    reviewer = {"Authorization": "Bearer tok-rev"}
    first = client.post("/threads/api-1/messages", json={"text": "lower budget"}, headers=requester)
    assert first.status_code == 200 and first.json()["interrupted"] is True
    proposal_id = first.json()["proposal"]["proposal_id"]
    assert (
        client.post("/threads/api-1/messages", json={"text": "hi"}, headers=reviewer).status_code
        == 403
    ), "thread ownership"
    assert client.post(f"/proposals/{proposal_id}/approve", headers=requester).status_code == 403
    edited = client.post(
        f"/proposals/{proposal_id}/edit", json={"changes": {"daily_budget": 250}}, headers=reviewer
    )
    assert edited.status_code == 200 and edited.json()["proposal"]["revision"] == 2
    approved = client.post(f"/proposals/{proposal_id}/approve", headers=reviewer)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["receipt"]["status"] == "verified" and body["proposal"]["revision"] == 2
    assert provider.mutation_calls[0][1]["daily_budget"] == 250
    fetched = client.get(f"/proposals/{proposal_id}", headers=reviewer).json()
    assert fetched["receipt"]["status"] == "verified"
    assert fastapi is not None


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
    }


async def test_self_hosted_runtime_uses_the_same_profile(
    settings: Settings, project_root: Path
) -> None:
    from paid_media_agent.runtime.self_hosted import build_self_hosted_runtime
    from paid_media_agent.testing.scripted_model import ScriptedChatModel

    runtime = await build_self_hosted_runtime(
        settings, project_root=project_root, model=ScriptedChatModel(steps=[])
    )
    assert runtime.persistence == "memory" and runtime.profile.name == "self_hosted"
    assert runtime.components.metadata.catalog_source == "fixture"
    assert runtime.profile.write_provider_is_fake is True
    assert {t.name for t in runtime.components.tools} >= {
        "discover_tools",
        "compare_periods",
        "render_report",
    }


async def test_signed_http_ack_precedes_agent_work_and_verifies_requests(
    settings: Settings, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    import hashlib
    import hmac
    import time
    from types import SimpleNamespace

    import httpx
    from pydantic import SecretStr
    from slack_sdk.web.async_client import AsyncWebClient
    from slack_sdk.web.async_slack_response import AsyncSlackResponse

    from paid_media_agent.surfaces.slack import socket_mode

    class Client(AsyncWebClient):
        async def auth_test(self, **kwargs):
            return AsyncSlackResponse(
                client=self,
                http_verb="POST",
                api_url="https://slack.com/api/auth.test",
                req_args={},
                data={"ok": True, "team_id": "T1", "user_id": "BOT", "bot_id": "B1"},
                headers={},
                status_code=200,
            )

    monkeypatch.setattr("slack_sdk.web.async_client.AsyncWebClient", Client)
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()

    async def slow_run(*args, **kwargs):
        started.set()
        await release.wait()
        finished.set()

    monkeypatch.setattr(socket_mode, "deliver", slow_run)
    configured = settings.model_copy(
        update={
            "slack_transport": "http",
            "slack_bot_token": SecretStr("xoxb-test"),
            "slack_signing_secret": SecretStr("test-signature"),
        }
    )
    runtime, _ = build_runtime(configured, project_root, [final_step])
    app = create_app(
        SimpleNamespace(
            settings=configured,
            graph=runtime.graph,
            components=runtime.components,
            profile=runtime.profile,
            catalog=runtime.catalog,
            persistence="memory",
            dedupe=InMemoryDedupeStore(),
            threads=InMemoryThreadOwnershipStore(),
        )
    )
    body = json.dumps(_slack_event("T1", "C1", "1.0", "U1", "Analyze spend", "Ev-ack")).encode()

    def headers(timestamp):
        signature = hmac.new(
            b"test-signature", b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
        return {
            "Content-Type": "application/json",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": f"v0={signature}",
        }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        assert (await client.post("/slack/events", content=body)).status_code == 401
        assert (
            await client.post(
                "/slack/events", content=body, headers=headers(str(int(time.time()) - 3600))
            )
        ).status_code == 401
        response = await asyncio.wait_for(
            client.post(
                "/slack/events",
                content=body,
                headers=headers(str(int(time.time()))),
            ),
            timeout=1,
        )
        assert response.status_code == 200
        await asyncio.wait_for(started.wait(), timeout=1)
        assert not finished.is_set()
        release.set()
        await asyncio.wait_for(finished.wait(), timeout=1)


async def test_artifacts_require_thread_owner_and_persisted_report_reference(
    settings: Settings, project_root: Path
) -> None:
    from types import SimpleNamespace

    import httpx
    from langchain_core.messages import ToolMessage
    from pydantic import SecretStr

    configured = settings.model_copy(
        update={"paid_media_api_tokens": SecretStr("alice-token:alice,bob-token:bob")}
    )
    runtime, _ = build_runtime(configured, project_root, [final_step])
    threads = InMemoryThreadOwnershipStore()
    threads.claim("alice-thread", "alice")
    output = runtime.profile.workspace_root / "out"
    (output / "report.html").write_text("<p>Alice's report</p>")
    (output / "other.html").write_text("<p>Other report</p>")
    await runtime.graph.aupdate_state(
        {"configurable": {"thread_id": "alice-thread", "caller_ref": "alice"}},
        {
            "messages": [
                ToolMessage(
                    name="render_report",
                    tool_call_id="report-1",
                    content=json.dumps({"files": [{"path": "report.html"}]}),
                )
            ]
        },
    )
    app = create_app(
        SimpleNamespace(
            settings=configured,
            graph=runtime.graph,
            components=runtime.components,
            profile=runtime.profile,
            catalog=runtime.catalog,
            persistence="memory",
            threads=threads,
        )
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        path = "/threads/alice-thread/artifacts/report.html"
        alice = {"Authorization": "Bearer alice-token"}
        bob = {"Authorization": "Bearer bob-token"}
        assert (await client.get(path, headers=alice)).text == "<p>Alice's report</p>"
        assert (await client.get(path, headers=bob)).status_code == 403
        assert (
            await client.get("/threads/alice-thread/artifacts/other.html", headers=alice)
        ).status_code == 404
        assert (await client.get("/artifacts/report.html", headers=alice)).status_code == 404
