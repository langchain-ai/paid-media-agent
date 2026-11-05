"""Slack step phrasing: analyst language in both tenses, no argument text, the turn's plan."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from paid_media_agent.surfaces.progress import (
    MAX_STEPS,
    TOOL_PHRASES,
    phrase,
    plan_from_state,
    plan_steps,
)
from paid_media_agent.tools.catalog import ToolClass
from paid_media_agent.tools.fixtures import build_fixture_catalog


@pytest.mark.parametrize(
    ("name", "args", "expected"),
    [
        (
            "google_ads__get_campaign_performance",
            {"account_alias": "acme-search"},
            ("Reading Google Ads campaign performance", "Read Google Ads campaign performance"),
        ),
        (
            "meta_ads__list_campaigns",
            {},
            ("Listing Meta Ads campaigns", "Listed Meta Ads campaigns"),
        ),
        ("compare_periods", {}, ("Comparing the two periods", "Compared the two periods")),
        ("execute_change", {}, ("Waiting for approval", "Finished the change review")),
        (
            "read_file",
            {"file_path": "/skills/paid-media-wiki/bidding-and-budget.md"},
            ("Reading the wiki on bidding and budget", "Read the wiki on bidding and budget"),
        ),
        (
            "read_file",
            {"file_path": "/skills/company-context/SKILL.md"},
            ("Reading your company context", "Read your company context"),
        ),
        (
            "start_async_task",
            {"subagent_type": "account-puller", "description": "Pull acme for 90 days"},
            ("Handing the account pull to a helper", "Handed the account pull to a helper"),
        ),
        ("mystery_tool", {}, ("Mystery tool", "Mystery tool")),
    ],
)
def test_phrases_read_as_analyst_work(
    name: str, args: dict[str, object], expected: tuple[str, str]
) -> None:
    assert phrase(name, args) == expected


def test_every_repository_tool_and_fixture_read_has_a_phrase() -> None:
    for name in (
        "list_accounts",
        "discover_tools",
        "summarize_window",
        "render_report",
        "propose_change",
        "schedule_check_in",
    ):
        assert name in TOOL_PHRASES
    for entry in build_fixture_catalog().entries:
        if entry.tool_class is ToolClass.READ:
            running, done = phrase(entry.qualified_name)
            assert "__" not in running and "_" not in done, entry.qualified_name


def test_phrases_never_carry_argument_text() -> None:
    secret = "acme-private-alias"
    for name in ("google_ads__get_campaign_performance", "propose_change", "start_async_task"):
        assert secret not in " ".join(
            phrase(name, {"account_alias": secret, "description": secret})
        )
    assert secret not in " ".join(phrase("read_file", {"file_path": f"/workspace/in/{secret}.csv"}))


def _call(name: str, call_id: str, **args: object) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_plan_shows_only_the_current_turn_with_status() -> None:
    messages = [
        HumanMessage("Earlier question"),
        _call("list_accounts", "old"),
        ToolMessage("{}", tool_call_id="old", name="list_accounts"),
        AIMessage("Earlier answer"),
        HumanMessage("How did Google do?"),
        _call("google_ads__get_campaign_performance", "c1"),
        ToolMessage("{}", tool_call_id="c1", name="google_ads__get_campaign_performance"),
        _call("compare_periods", "c2"),
        ToolMessage("{}", tool_call_id="c2", name="compare_periods", status="error"),
        _call("render_report", "c3"),
    ]
    assert plan_steps(messages) == [
        {"title": "Read Google Ads campaign performance", "status": "complete"},
        {"title": "Compared the two periods", "status": "error"},
        {"title": "Rendering the report", "status": "in_progress"},
    ]


def test_plan_chooser_leaves_slack_alone_until_there_is_a_step() -> None:
    assert plan_from_state({"state": {"messages": [HumanMessage("hi")]}}) is None
    assert plan_from_state({"state": {}}) is None
    many = [HumanMessage("go"), *(_call("list_accounts", f"c{i}") for i in range(MAX_STEPS + 4))]
    plan = plan_from_state({"state": {"messages": many}})
    assert plan is not None and len(plan) == MAX_STEPS


def test_slack_channel_declares_the_plan_and_thread_mode(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PAID_MEDIA_SLACK_TRIGGER_MODE", raising=False)
    monkeypatch.chdir(project_root)
    channel = runpy.run_path(str(project_root / "channels/slack.py"))["channel"]
    assert channel.status is plan_from_state
    assert channel.trigger_mode == "thread"
    assert channel.trigger_on_all_messages is False
