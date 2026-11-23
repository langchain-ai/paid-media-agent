"""Background helpers on MDA: the lead's choice of model, the worker's swap, and progress notes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain.agents.middleware.types import ModelRequest, ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.runtime import Runtime
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command
from pydantic import BaseModel

from paid_media_agent.assembly import build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.middleware import async_helpers
from paid_media_agent.middleware.async_helpers import (
    CHOICE_KEY,
    NOTES,
    AsyncHelpersMiddleware,
    HelperChoice,
    HelperModels,
    WorkerModelMiddleware,
    choose_helper_model,
    helper_config,
    notes_message,
    report_progress,
)
from paid_media_agent.middleware.footer import _turn, person_turn
from paid_media_agent.runtime.profiles import fixture_profile
from paid_media_agent.testing.scripted_model import ScriptedChatModel
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.fixtures import build_fixture_catalog
from tests.contract.helpers import config

LEAD = "anthropic:claude-opus-5-5"


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {"paid_media_model": LEAD, "paid_media_model_effort": "high"}
    return Settings(_env_file=None, **(values | overrides))  # type: ignore[call-arg]


def _no_build(_choice: HelperChoice) -> Any:
    raise AssertionError("the lead's own model is not rebuilt")


def _built(_choice: HelperChoice) -> Any:
    return object()


def test_an_empty_choice_is_the_leads_model_and_effort_without_building_it() -> None:
    assert choose_helper_model(_settings(), "", "", build=_no_build) == HelperChoice(LEAD, "high")


def test_the_helper_default_and_the_effort_cap_apply(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _settings(
        paid_media_helper_model="openai:gpt-5.5-mini", paid_media_helper_effort_cap="medium"
    )
    picked = choose_helper_model(settings, "", "max", build=_built)
    assert picked == HelperChoice("openai:gpt-5.5-mini", "medium")


def test_with_no_effort_named_a_helper_runs_at_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _settings(paid_media_model_effort=None, paid_media_helper_effort_cap="low")
    picked = choose_helper_model(settings, "openai:gpt-5.5", "", build=_built)
    assert picked == HelperChoice("openai:gpt-5.5", "low")


def test_the_leads_effort_carries_only_within_its_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _settings(paid_media_model_effort="max")
    same = choose_helper_model(settings, "anthropic:claude-sonnet-5-5", "", build=_built)
    assert same == HelperChoice("anthropic:claude-sonnet-5-5", "max")
    other = choose_helper_model(settings, "openai:gpt-5.5", "", build=_built)
    assert other == HelperChoice("openai:gpt-5.5", None), "the model's own default"
    asked = choose_helper_model(settings, "openai:gpt-5.5", "max", build=_built)
    assert asked == HelperChoice("openai:gpt-5.5", "xhigh"), "OpenAI has no max"


def test_a_proxys_key_never_reaches_another_host(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lead's endpoint and key variable travel together, only where they work."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("PROXY_KEY", "proxy-secret")
    settings = _settings(
        paid_media_model="openai:gpt-5.5",
        paid_media_model_effort=None,
        paid_media_model_base_url="https://proxy.example/v1",
        paid_media_model_api_key_env="PROXY_KEY",
    )
    own, own_key = helper_config(settings, "openai:gpt-5.5")
    assert str(own.base_url) == "https://proxy.example/v1" and own_key == "PROXY_KEY"
    other, other_key = helper_config(settings, "openai:gpt-5.5-mini")
    assert other.base_url is None and other_key is None
    picked = choose_helper_model(settings, "openai:gpt-5.5-mini", "", build=_built)
    assert isinstance(picked, str) and "needs OPENAI_API_KEY" in picked
    gateway = _settings(
        paid_media_model="langsmith:anthropic/claude-opus-5-5",
        paid_media_model_api_key_env="LANGSMITH_GATEWAY_API_KEY",
    )
    assert helper_config(gateway, "langsmith:openai/gpt-5.5")[1] == "LANGSMITH_GATEWAY_API_KEY"


def test_the_worker_checks_a_stamp_again_and_falls_back_whole(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stamp is run context a caller can write: the worker re-checks it, and a refused or
    unbuildable one runs on the default model with the default's tool selection."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = _settings(paid_media_helper_effort_cap="low")
    default = HelperChoice(LEAD, "low")

    def build(choice: HelperChoice) -> Any:
        if choice.model == "openai:gpt-broken":
            raise RuntimeError("no such model")
        return choice

    models = HelperModels(
        build,
        lambda stamp: choose_helper_model(settings, stamp.model, stamp.effort or "", build=_built),
        default,
    )
    resolved = models.resolve(HelperChoice("openai:gpt-5.5", "max"))
    assert resolved is not None and resolved[0] == HelperChoice("openai:gpt-5.5", "low")
    assert models.resolve(HelperChoice("openai:gpt-broken", "low")) is None
    assert models.resolve(HelperChoice("not-a-model", None)) is None
    assert models.resolve(HelperChoice(LEAD, "max")) is None, "capped to the lead's own choice"


def test_a_provider_without_effort_runs_at_its_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    picked = choose_helper_model(_settings(), "google_genai:gemini-4-argon", "low", build=_built)
    assert picked == HelperChoice("google_genai:gemini-4-argon", None)


@pytest.mark.parametrize(
    ("model", "effort", "says"),
    [
        ("gpt-without-provider", "", "is not a provider:model id"),
        ("anthropic:claude-sonnet-5-5", "turbo", "effort 'turbo' is not one of"),
        ("openai:gpt-5.5", "", "needs OPENAI_API_KEY, which is not set"),
    ],
)
def test_a_refused_choice_says_what_to_fix(
    model: str, effort: str, says: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    picked = choose_helper_model(_settings(), model, effort, build=_built)
    assert isinstance(picked, str) and picked.startswith("Not started:") and says in picked


def test_a_model_that_does_not_build_is_refused_without_echoing_its_input() -> None:
    class Strict(BaseModel):
        api_key: int

    def build(_choice: HelperChoice) -> Any:
        Strict(api_key="sk-secret-value")  # type: ignore[arg-type]

    picked = choose_helper_model(_settings(), "anthropic:claude-sonnet-5-5", "", build=build)
    assert isinstance(picked, str) and "cannot run here" in picked
    assert "sk-secret-value" not in picked


def _start_tool() -> StructuredTool:
    async def start(description: str, subagent_type: str) -> str:
        return f"{subagent_type}: {description}"

    return StructuredTool.from_function(
        coroutine=start,
        name="start_async_task",
        description=(
            "Launch a task.\n\nAvailable async agent types:\n- worker: x\n- general-purpose: y\n\n"
            "## Usage notes:\n1. Do not check right away."
        ),
    )


def _middleware(choose: Any = None) -> AsyncHelpersMiddleware:
    return AsyncHelpersMiddleware(
        _settings(), choose or (lambda model, effort: HelperChoice(model or LEAD, effort or None))
    )


def test_the_lead_sees_a_model_an_effort_and_a_role_instead_of_agent_types() -> None:
    shown = _middleware()._shown(_start_tool())
    schema = shown.tool_call_schema.model_json_schema()["properties"]
    assert {"description", "model", "effort", "name"} <= schema.keys()
    assert "subagent_type" not in schema
    assert "general-purpose" not in shown.description and "provider:model" in shown.description
    assert "## Usage notes:" in shown.description


def _tool_request(name: str, args: dict[str, Any], **state: Any) -> ToolCallRequest:
    runtime = ToolRuntime(
        state=state,
        context={"deepagents_parent": {"thread_id": "x"}, "mda_channel": {"name": "slack"}},
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id="call-1",
        store=None,
    )
    call = {"name": name, "args": args, "id": "call-1", "type": "tool_call"}
    return ToolCallRequest(tool_call=call, tool=None, state=state, runtime=runtime)  # type: ignore[arg-type]


async def test_start_runs_on_the_worker_with_the_choice_on_its_context_and_record() -> None:
    seen: list[ToolCallRequest] = []

    async def handler(request: ToolCallRequest) -> Command[Any]:
        seen.append(request)
        task = {"task_id": "t-1", "agent_name": "worker", "status": "running"}
        return Command(update={"async_tasks": {"t-1": task}, "messages": []})

    args = {"description": "Pull acme", "model": "openai:gpt-5.5", "effort": "low"}
    request = _tool_request("start_async_task", {**args, "name": "  Acme   pull "})
    result = await _middleware().awrap_tool_call(request, handler)

    sent = seen[0]
    assert sent.tool_call["args"] == {"description": "Pull acme", "subagent_type": "worker"}
    chosen = {"model": "openai:gpt-5.5", "effort": "low", "name": "Acme pull"}
    assert sent.runtime.context[CHOICE_KEY] == chosen
    assert sent.runtime.context["mda_channel"] == {"name": "slack"}, "forwarded as deepagents does"
    assert "deepagents_parent" not in sent.runtime.context
    assert isinstance(result, Command)
    assert result.update["async_tasks"]["t-1"][CHOICE_KEY] == chosen  # type: ignore[index]


async def test_a_refused_choice_starts_nothing() -> None:
    async def handler(_request: ToolCallRequest) -> Any:
        raise AssertionError("nothing starts")

    middleware = _middleware(lambda _m, _e: "Not started: no key")
    result = await middleware.awrap_tool_call(
        _tool_request("start_async_task", {"description": "x"}), handler
    )
    assert isinstance(result, ToolMessage) and result.status == "error"
    assert result.content == "Not started: no key"


async def test_a_follow_up_keeps_the_model_the_task_started_on() -> None:
    seen: list[ToolCallRequest] = []

    async def handler(request: ToolCallRequest) -> ToolMessage:
        seen.append(request)
        return ToolMessage("ok", tool_call_id="call-1")

    chosen = {"model": "openai:gpt-5.5", "effort": "low", "name": "Acme pull"}
    tasks = {"t-1": {"task_id": "t-1", CHOICE_KEY: chosen}}
    request = _tool_request("update_async_task", {"task_id": " t-1 ", "message": "Add Meta"})
    request = request.override(state={"async_tasks": tasks})
    await _middleware().awrap_tool_call(request, handler)
    assert seen[0].runtime.context[CHOICE_KEY] == chosen


def _model_request(context: Any, model: Any) -> ModelRequest[Any]:
    return ModelRequest(
        model=model,
        messages=[HumanMessage("x")],
        runtime=Runtime(context=context),  # type: ignore[arg-type]
    )


def test_the_worker_runs_each_call_on_the_stamped_model() -> None:
    lead_model, helper_model = object(), object()
    default = HelperChoice(LEAD, "high")
    built: list[HelperChoice] = []
    models = HelperModels(
        lambda choice: built.append(choice) or helper_model,  # type: ignore[arg-type,func-returns-value]
        lambda stamp: stamp,
        default,
    )
    swap = WorkerModelMiddleware(models)

    def model_of(context: Any) -> Any:
        return swap.wrap_model_call(_model_request(context, lead_model), lambda r: r.model)

    stamp = {CHOICE_KEY: {"model": "openai:gpt-5.5", "effort": "low", "name": ""}}
    assert model_of(stamp) is helper_model
    assert model_of(stamp) is helper_model and len(built) == 1, "built once per choice"
    assert model_of({CHOICE_KEY: {"model": LEAD, "effort": "high"}}) is lead_model
    assert model_of(None) is lead_model


def _tool_runtime(store: Any, **configurable: Any) -> ToolRuntime:
    return ToolRuntime(
        state={},
        context={CHOICE_KEY: {"model": "openai:gpt-5.5", "effort": "low", "name": "Meta pull"}},
        config={"configurable": configurable, "metadata": {}},
        stream_writer=lambda _chunk: None,
        tool_call_id="call-1",
        store=store,
    )


PARENT = {"deepagents_parent": {"thread_id": "lead-1", "assistant_id": "asst-1"}}


async def test_a_note_waits_for_the_lead_under_its_thread() -> None:
    store = InMemoryStore()
    answer = await report_progress(
        "Google done; Meta next, ~2 min.", _tool_runtime(store, **PARENT)
    )
    assert "before its next step" in answer
    (item,) = await store.asearch((*NOTES, "lead-1"))
    assert item.value["task"] == "Meta pull" and item.value["urgent"] is False


async def test_a_task_without_a_lead_keeps_its_note_for_the_summary() -> None:
    answer = await report_progress("x", _tool_runtime(InMemoryStore()))
    assert "no lead" in answer


class _Client:
    def __init__(self, status: str) -> None:
        self.status = status
        self.created: list[dict[str, Any]] = []
        self.threads, self.runs = self, self

    async def get(self, *, thread_id: str) -> dict[str, Any]:
        return {"thread_id": thread_id, "status": self.status}

    async def create(self, thread_id: str, assistant_id: str, **kwargs: Any) -> dict[str, Any]:
        self.created.append({"thread_id": thread_id, "assistant_id": assistant_id, **kwargs})
        return {}


async def test_an_urgent_note_wakes_an_idle_lead(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _Client("idle")
    monkeypatch.setattr(async_helpers, "get_client", lambda: client)
    store = InMemoryStore()
    answer = await report_progress(
        "Meta has no data for March.", _tool_runtime(store, **PARENT), urgent=True
    )
    assert answer == "Sent; the lead was woken for it."
    (run,) = client.created
    assert run["thread_id"] == "lead-1" and run["assistant_id"] == "asst-1"
    assert run["multitask_strategy"] == "reject"
    (message,) = run["input"]["messages"]
    assert message["additional_kwargs"] == {async_helpers.NOTES_KEY: True}
    assert "Meta pull (urgent): Meta has no data for March." in message["content"]
    assert CHOICE_KEY not in (run["context"] or {})
    assert not await store.asearch((*NOTES, "lead-1")), "the woken run carries the note"


async def test_an_urgent_note_waits_while_the_lead_is_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Client("busy")
    monkeypatch.setattr(async_helpers, "get_client", lambda: client)
    store = InMemoryStore()
    answer = await report_progress("Blocked.", _tool_runtime(store, **PARENT), urgent=True)
    assert "before its next step" in answer and not client.created
    assert len(await store.asearch((*NOTES, "lead-1"))) == 1


def test_notes_are_neither_a_persons_turn_nor_a_turn_boundary() -> None:
    person = HumanMessage("How did Meta do?")
    notes = notes_message([{"task": "Meta pull", "note": "Half done."}])
    tool = ToolMessage("read", tool_call_id="c-1")
    assert not person_turn([person, notes])
    assert person_turn([notes, person])
    assert list(_turn([person, AIMessage(""), tool, notes])) == [AIMessage(""), tool, notes]


async def test_the_lead_reads_its_notes_before_its_next_model_call(
    settings: Settings, project_root: Path
) -> None:
    store = InMemoryStore()
    note = {"task": "Meta pull", "note": "Meta done; Google next.", "urgent": False, "at": 1.0}
    await store.aput((*NOTES, "lead-1"), "n-1", note)
    seen: list[list[Any]] = []

    def answer(messages: Any) -> AIMessage:
        seen.append(list(messages))
        return AIMessage(content="Meta is in; Google is next.")

    catalog = build_fixture_catalog()
    components = build_agent_components(
        settings=settings,
        runtime=fixture_profile(
            settings,
            project_root=project_root,
            catalog_provider=StaticCatalogProvider(catalog),
            workspace_root=settings.paid_media_workspace_root,
        ),
        catalog=catalog,
        model=ScriptedChatModel(steps=[answer]),
        managed=True,
    )
    graph = create_deep_agent(
        components.model,
        list(components.tools),
        middleware=list(components.middleware),
        backend=FilesystemBackend(root_dir=project_root, virtual_mode=True),
        store=store,
    )
    await graph.ainvoke({"messages": [HumanMessage("How is it going?")]}, config("lead-1"))
    texts = [m.text for m in seen[0] if isinstance(m, HumanMessage)]
    assert any("Meta pull: Meta done; Google next." in text for text in texts)
    assert not await store.asearch((*NOTES, "lead-1")), "a note is read once"


def test_the_worker_picks_tool_selection_for_the_model_it_runs_on(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider tool search exists on the lead's model, not on Gemini: a Gemini task gets the
    portable selector instead."""
    from langchain.agents.middleware import ProviderToolSearchMiddleware

    from paid_media_agent.middleware.async_helpers import WorkerSelectionMiddleware
    from paid_media_agent.middleware.tool_selection import PortableToolSelectorMiddleware

    monkeypatch.setenv("GOOGLE_API_KEY", "g-test")
    settings = _settings(paid_media_workspace_root=tmp_path / "workspace")
    catalog = build_fixture_catalog()
    components = build_agent_components(
        settings=settings,
        runtime=fixture_profile(
            settings,
            project_root=project_root,
            catalog_provider=StaticCatalogProvider(catalog),
            workspace_root=settings.paid_media_workspace_root,
        ),
        catalog=catalog,
        model=ScriptedChatModel(steps=[]),
        managed=True,
    )
    (selection,) = (
        m
        for m in components.helpers["worker"]["middleware"]
        if isinstance(m, WorkerSelectionMiddleware)
    )
    gemini = {CHOICE_KEY: {"model": "google_genai:gemini-4-argon", "effort": "", "name": ""}}
    assert isinstance(selection._pick(_model_request(gemini, None)), PortableToolSelectorMiddleware)
    assert isinstance(selection._pick(_model_request(None, None)), ProviderToolSearchMiddleware)
