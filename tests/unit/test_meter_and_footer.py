"""The cost meter and the Slack footer: priced estimates, lead plus helpers, one line per reply."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.store.memory import InMemoryStore

from paid_media_agent.config import Settings
from paid_media_agent.middleware.footer import FOOTER_KEY, NOTIFICATION_KEY, footer_line
from paid_media_agent.middleware.meter import Meter, cost_of, load_prices, price_for
from paid_media_agent.testing.scripted_model import tool_call_message
from tests.contract.helpers import build_runtime


def test_prices_match_bare_dated_and_prefixed_names() -> None:
    sonnet = price_for("anthropic:claude-sonnet-4-6")
    assert sonnet is not None and sonnet.input == 3.0 and sonnet.output == 15.0
    assert price_for("claude-sonnet-4-6-20260217") == sonnet
    assert price_for("google_genai:gemini-3-flash-preview") == load_prices()["gemini-3-flash"]
    assert price_for("openai:kimi-k2-0905-preview") is None, "unlisted models are never guessed"
    assert price_for("openai:gpt-5.5-mini") is None and price_for("gpt-5.5-pro") is None
    assert price_for("gemini-3-flash-lite") is None


def test_cost_prices_cache_reads_and_writes_apart() -> None:
    price = price_for("claude-sonnet-4-6")
    assert price is not None
    usage = {
        "input_tokens": 100_000,
        "output_tokens": 2_000,
        "input_token_details": {"cache_read": 80_000, "cache_creation": 10_000},
    }
    # 10k uncached at $3, 80k read at $0.30, 10k written at $3.75, 2k out at $15 (per million).
    assert cost_of(usage, price) == pytest.approx(0.03 + 0.024 + 0.0375 + 0.03)
    haiku = price_for("claude-haiku-5-5")
    assert haiku is not None
    long = {"input_tokens": 200_000, "output_tokens": 0}
    assert cost_of(long, haiku) == pytest.approx(0.10), "long prompts pay long-context prices"


def _message(model: str, tokens: int) -> AIMessage:
    return AIMessage(
        content="x",
        usage_metadata={"input_tokens": tokens, "output_tokens": 0, "total_tokens": tokens},
        response_metadata={"model_name": model},
    )


async def test_meter_sums_a_lead_and_its_helpers_without_sharing_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import paid_media_agent.middleware.meter as meter_module

    store = InMemoryStore()
    meter = Meter()
    lead = SimpleNamespace(store=store, thread=SimpleNamespace(id="lead-thread"))
    monkeypatch.setattr(meter_module, "run_thread", lambda: "lead-thread")
    await meter.record(lead, _message("claude-sonnet-4-6", 1_000_000))
    # An MDA helper's runtime.thread is its lead's; its own run thread differs.
    monkeypatch.setattr(meter_module, "run_thread", lambda: "helper-task-thread")
    await meter.record(lead, _message("claude-sonnet-4-6", 1_000_000))
    await meter.record(lead, _message("unlisted-model", 10))
    await meter.record(lead, AIMessage(content="retry failed"))  # no usage: not a billed call
    totals = await meter.totals(lead)
    assert totals.usd == pytest.approx(6.0) and totals.calls == 3 and totals.unpriced == 1
    keys = {item.key for item in await store.asearch(("paid_media_agent", "meter", "lead-thread"))}
    assert keys == {"lead", "helper-task-thread"}


def test_footer_line_says_only_what_changes() -> None:
    assert footer_line(minutes=0.4, usd=0.031) == "_<1 min · ~$0.03_"
    assert (
        footer_line(minutes=3.2, usd=0.12, running=1)
        == "_1 helper running · 3 min · ~$0.12 so far_"
    )
    assert footer_line(minutes=6, usd=0.41, helpers=2) == "_2 helpers · 6 min · ~$0.41_"
    assert footer_line(minutes=2, usd=None) == "_2 min_", "an incomplete estimate shows no cost"


def _slack(thread: str) -> RunnableConfig:
    return RunnableConfig(
        configurable={"thread_id": thread, "caller_ref": "local-user", "surface": "slack"}
    )


async def test_slack_reply_gets_a_footer_the_model_never_reads_back(
    settings: Settings, project_root: Path
) -> None:
    seen: list[list[BaseMessage]] = []

    def second_turn(messages: Any) -> AIMessage:
        seen.append(list(messages))
        return AIMessage(content="Nothing else changed.")

    steps = [
        lambda _m: tool_call_message("list_accounts", {}),
        lambda _m: AIMessage(content="Three accounts are connected."),
        lambda _m: tool_call_message("list_accounts", {}),
        second_turn,
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    cfg = _slack("slack-footer")
    state = await runtime.graph.ainvoke({"messages": [HumanMessage("Which accounts?")]}, cfg)
    reply = state["messages"][-1]
    assert reply.content.startswith("Three accounts are connected.\n\n_")
    assert reply.additional_kwargs[FOOTER_KEY] == "_<1 min · ~$0.00_", "a scripted model is free"
    await runtime.graph.ainvoke({"messages": [HumanMessage("Anything else?")]}, cfg)
    earlier = [m for m in seen[0] if isinstance(m, AIMessage) and m.content]
    assert earlier and all("<1 min" not in str(m.content) for m in earlier)


async def test_footer_skips_api_runs_chat_without_work_and_quiet_replies(
    settings: Settings, project_root: Path
) -> None:
    steps = [
        lambda _m: tool_call_message("list_accounts", {}),
        lambda _m: AIMessage(content="Three accounts."),
        lambda _m: AIMessage(content="Hello!"),
        lambda _m: tool_call_message("list_accounts", {}),
        lambda _m: AIMessage(content="[quiet]"),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    api = RunnableConfig(configurable={"thread_id": "api-thread", "caller_ref": "local-user"})
    state = await runtime.graph.ainvoke({"messages": [HumanMessage("Which accounts?")]}, api)
    assert FOOTER_KEY not in state["messages"][-1].additional_kwargs
    cfg = _slack("slack-chat")
    state = await runtime.graph.ainvoke({"messages": [HumanMessage("hi")]}, cfg)
    assert state["messages"][-1].content == "Hello!"
    state = await runtime.graph.ainvoke({"messages": [HumanMessage("anything?")]}, cfg)
    assert state["messages"][-1].content == "[quiet]"


async def test_a_helper_notification_keeps_counting_the_request_that_started_it(
    settings: Settings, project_root: Path
) -> None:
    steps = [
        lambda _m: tool_call_message("list_accounts", {}),
        lambda _m: AIMessage(content="Started the pull."),
        lambda _m: AIMessage(content="The pull finished: spend rose 8%."),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    meter = runtime.components.meter
    cfg = _slack("slack-job")
    await runtime.graph.ainvoke({"messages": [HumanMessage("Pull every account")]}, cfg)
    job = await meter.job(SimpleNamespace(thread=SimpleNamespace(id="slack-job")))
    assert job is not None
    notification = HumanMessage(
        "<task-notification>done</task-notification>",
        additional_kwargs={NOTIFICATION_KEY: {"task_id": "t1", "status": "success"}},
    )
    state = await runtime.graph.ainvoke({"messages": [notification]}, cfg)
    assert state["messages"][-1].additional_kwargs.get(FOOTER_KEY) is None, "a wake-up with no work"
    again = await meter.job(SimpleNamespace(thread=SimpleNamespace(id="slack-job")))
    assert again == job, "a notification is not a new request"


async def test_footer_counts_helpers_running_on_an_mda_slack_thread() -> None:
    from paid_media_agent.middleware.footer import RunFooterMiddleware

    clock = [1_000.0]
    meter = Meter(clock=lambda: clock[0])
    slack = SimpleNamespace(provider="slack")
    runtime = SimpleNamespace(
        store=InMemoryStore(),
        thread=SimpleNamespace(id="mda-thread", origin=SimpleNamespace(channel=slack)),
    )
    await meter.start_job(runtime)
    clock[0] += 185
    middleware = RunFooterMiddleware(meter)
    state: dict[str, Any] = {
        "messages": [HumanMessage("Pull all accounts"), AIMessage(content="Two helpers started.")],
        "async_tasks": {
            "t1": {"status": "running", "created_at": "2099-01-01T00:00:00Z"},
            "t2": {"status": "success", "created_at": "2099-01-01T00:00:00Z"},
            "old": {"status": "success", "created_at": "1970-01-01T00:00:00Z"},
        },
    }
    update = await middleware.aafter_agent(state, runtime)  # type: ignore[arg-type]
    assert update is not None
    assert update["messages"][0].additional_kwargs[FOOTER_KEY] == (
        "_1 helper running · 3 min · ~$0.00 so far_"
    )
    elsewhere = SimpleNamespace(
        store=runtime.store,
        thread=SimpleNamespace(
            id="mda-thread", origin=SimpleNamespace(channel=SimpleNamespace(provider="github"))
        ),
    )
    assert await middleware.aafter_agent(state, elsewhere) is None  # type: ignore[arg-type]


def test_default_and_preset_models_are_priced_and_registered() -> None:
    from paid_media_agent.admin.model_presets import MODEL_PRESETS
    from paid_media_agent.config import DEFAULT_MODEL_SPEC, ModelConfig
    from paid_media_agent.middleware.tool_selection import CAPABILITY_REGISTRY, capabilities_for

    assert DEFAULT_MODEL_SPEC == "anthropic:claude-fable-5-1"
    assert capabilities_for(ModelConfig.parse(DEFAULT_MODEL_SPEC)).native_tool_search
    for preset in MODEL_PRESETS:
        if preset["id"] in ("anthropic", "openai", "google"):
            spec = str(preset["model"])
            assert spec in CAPABILITY_REGISTRY, spec
            assert price_for(spec) is not None, spec
