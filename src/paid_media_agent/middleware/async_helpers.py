"""Background helpers on Managed Deep Agents: MDA's async subagents, on the model the lead picks.

MDA 0.10 runs each subagent declared `"async": True` as its own graph on the Agent Server, on a
thread of its own that shares the lead's sandbox and trace, and gives the lead deepagents' tools
for it: `start_async_task`, `check_async_task`, `update_async_task`, `cancel_async_task` and
`list_async_tasks`. A task survives a deploy, and deepagents wakes an idle lead when one ends.
Every task runs on `worker` (`subagents.py`), and the lead picks each task's model and effort:

- `AsyncHelpersMiddleware` (the lead's) shows `start_async_task` with `model`, `effort` and `name`
  in place of `subagent_type`, checks the choice (`choose_helper_model`), and stamps it on the run
  context deepagents forwards to the task's run. `update_async_task` continues a task on the
  choice it started with, kept on the task's record in `async_tasks`. Before each model call it
  hands the lead the progress notes its tasks sent.
- `WorkerModelMiddleware` (first in the worker's own stack) swaps the stamped model in on every
  call, and `WorkerSelectionMiddleware` picks tool selection for that model: provider tool search
  only exists on some models. A run with no stamp keeps the worker's own model, the lead's.
- `WorkerNotesMiddleware` gives the worker `report_progress`. A note waits in the deployment's
  store under the lead's thread. An urgent note also wakes an idle lead, the way deepagents does
  when a task ends: a run on the lead's thread through the Agent Server's own client.

MDA builds an async subagent's graph from a static spec, so a model cannot be declared per task;
the choice travels on the run context instead. A note or a role name is model text: it reaches
the lead's model, never a Slack status line (`surfaces/progress.py`).
"""

from __future__ import annotations

import dataclasses
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from deepagents.middleware.async_subagents import StartAsyncTaskSchema
from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain.tools import ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.config import get_config
from langgraph.types import Command
from langgraph_sdk import get_client
from pydantic import BaseModel, Field, ValidationError
from pydantic.json_schema import SkipJsonSchema

from paid_media_agent.config import (
    EFFORT_PROVIDERS,
    EFFORTS,
    PROVIDER_DEFAULT_KEYS,
    ModelConfig,
    Settings,
)
from paid_media_agent.subagents import REPORT_PROGRESS_TOOL, WORKER

_LOGGER = logging.getLogger(__name__)

#: Where the lead's choice travels on the task's run context and its record.
CHOICE_KEY = "paid_media_helper"
START, UPDATE = "start_async_task", "update_async_task"
#: Where a worker's progress notes wait for its lead, under the lead's thread id.
NOTES = ("paid_media_agent", "helper_notes")
#: Marks a message of helper notes: not from a person (`middleware/footer.py`).
NOTES_KEY = "paid_media_helper_notes"
#: Lead thread statuses a wake-up run can start on: neither running nor waiting for a person.
_WAKEABLE = frozenset({"idle", "error"})
#: deepagents' key for an async run's parent reference, which it adds itself.
_PARENT_KEY = "deepagents_parent"
#: Where deepagents' description lists its agent types, which the lead sees as a choice instead.
_TYPES_HEAD, _USAGE_HEAD = "Available async agent types:", "## Usage notes:"
_NOTE_CHARS, _NAME_CHARS, _NOTES_READ = 600, 40, 50


@dataclass(frozen=True)
class HelperChoice:
    """What a helper runs on: a normalized `provider:model`, and an effort when it takes one."""

    model: str
    effort: str | None


BuildModel = Callable[[HelperChoice], BaseChatModel]


def lead_choice(settings: Settings) -> HelperChoice:
    """The lead's own model and effort: what a helper with no stamp runs on."""
    return HelperChoice(settings.model_settings().spec, settings.paid_media_model_effort)


def helper_config(settings: Settings, model: str) -> tuple[ModelConfig, str | None]:
    """A helper model's config and the env var holding its key.

    The lead's endpoint (`PAID_MEDIA_MODEL_BASE_URL`) and key variable
    (`PAID_MEDIA_MODEL_API_KEY_ENV`) travel together, and only where they are known to work: the
    lead's own model, or another model of its provider when the lead uses the provider's own
    endpoint. Anything else gets the provider's defaults, so a proxy's key never reaches another
    host.
    """
    lead = settings.model_settings()
    carried = _carries_lead_access(lead, ModelConfig.parse(model))
    config = ModelConfig.parse(
        model,
        base_url=str(lead.base_url) if carried and lead.base_url is not None else None,
        tool_selector_model=settings.paid_media_tool_selector_model,
    )
    return config, settings.paid_media_model_api_key_env if carried else None


def _carries_lead_access(lead: ModelConfig, config: ModelConfig) -> bool:
    return config.spec == lead.spec or (config.provider == lead.provider and lead.base_url is None)


def choose_helper_model(
    settings: Settings, model: str, effort: str, *, build: BuildModel
) -> HelperChoice | str:
    """The model and effort a helper runs on, or a short reason the lead can act on.

    `model` is any `provider:model` (or `langsmith:provider/model`) LangChain can build here;
    empty, `PAID_MEDIA_HELPER_MODEL`, else the lead's. `effort` is one of `EFFORTS`; empty, the
    lead's when the provider is the lead's, else `PAID_MEDIA_HELPER_EFFORT_CAP` when set, else the
    model's default. Over the cap it runs at the cap; OpenAI has no `max` and runs at `xhigh`; a
    provider that takes no effort runs at its default. A model other than the lead's is built to
    check it (no network call), and needs its key unless it uses the lead's (`helper_config`).
    """
    text = model.strip() or settings.paid_media_helper_model or settings.paid_media_model
    try:
        config = ModelConfig.parse(text)
    except ValueError:
        return f"Not started: {text!r} is not a provider:model id, like anthropic:claude-opus-5-5."
    asked = effort.strip().lower()
    if asked and asked not in EFFORTS:
        return f"Not started: effort {asked!r} is not one of {', '.join(EFFORTS)}."
    lead_config = settings.model_settings()
    if not asked and config.provider == lead_config.provider:
        asked = settings.paid_media_model_effort or ""
    cap = settings.paid_media_helper_effort_cap
    if cap and (not asked or EFFORTS.index(asked) > EFFORTS.index(cap)):
        asked = cap
    if config.provider == "openai" and asked == "max":
        asked = "xhigh"
    chosen = HelperChoice(
        config.spec, (asked or None) if config.provider in EFFORT_PROVIDERS else None
    )
    lead = lead_choice(settings)
    if chosen == lead:
        return chosen
    try:
        build(chosen)
    except Exception as error:
        return f"Not started: {config.spec} cannot run here: {_why(error)}"
    needed = PROVIDER_DEFAULT_KEYS.get(config.provider)
    if not _carries_lead_access(lead_config, config) and needed and not os.environ.get(needed):
        return f"Not started: {config.spec} needs {needed}, which is not set."
    return chosen


def _why(error: Exception) -> str:
    """An error's first line, without the input a validation error echoes (it can hold a key)."""
    if isinstance(error, ValidationError):
        found = error.errors(include_input=False, include_url=False)
        return str(found[0]["msg"]) if found else type(error).__name__
    return (str(error).splitlines() or [type(error).__name__])[0][:200]


class HelperModels:
    """The worker's side of a choice: checked again and built once per stamp.

    A stamp is run context, which any caller allowed to start runs on the deployment can write, so
    the worker runs it through the same check as the lead (`check`, the cap included). A refused or
    unbuildable stamp, or one that is the lead's own, runs on the worker's default model. A model
    holds no run's state, so one instance serves every task on that choice.
    """

    def __init__(
        self,
        build: BuildModel,
        check: Callable[[HelperChoice], HelperChoice | str],
        default: HelperChoice,
    ) -> None:
        self._build, self._check, self.default = build, check, default
        self._resolved: dict[HelperChoice, tuple[HelperChoice, BaseChatModel] | None] = {}

    def resolve(self, stamp: HelperChoice) -> tuple[HelperChoice, BaseChatModel] | None:
        """The checked choice and its model, or None for the default."""
        if stamp not in self._resolved:
            self._resolved[stamp] = self._resolved_now(stamp)
        return self._resolved[stamp]

    def _resolved_now(self, stamp: HelperChoice) -> tuple[HelperChoice, BaseChatModel] | None:
        picked = self._check(stamp)
        if isinstance(picked, str):
            _LOGGER.warning("[worker] %s refused; using the default: %s", stamp.model, picked)
            return None
        if picked == self.default:
            return None
        try:
            return picked, self._build(picked)
        except Exception:
            _LOGGER.warning("[worker] %s no longer builds; using the default", picked.model)
            return None


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    return value if isinstance(value, Mapping) else None


def stamped(context: object) -> HelperChoice | None:
    """The choice stamped on a run context or a task record, or None."""
    data = _as_mapping(context)
    chosen = data.get(CHOICE_KEY) if data is not None else None
    if not isinstance(chosen, Mapping) or not isinstance(chosen.get("model"), str):
        return None
    effort = chosen.get("effort")
    return HelperChoice(chosen["model"], effort if isinstance(effort, str) and effort else None)


def helper_label(context: object) -> str:
    """How the lead is told which helper wrote: the role it named, else the model."""
    data = _as_mapping(context)
    chosen = data.get(CHOICE_KEY) if data is not None else None
    if not isinstance(chosen, Mapping):
        return ""
    name, model = chosen.get("name"), chosen.get("model")
    if isinstance(name, str) and name:
        return name
    return f"Helper on {str(model).rpartition('/')[2].rpartition(':')[2]}" if model else ""


def forwarded(context: object) -> dict[str, Any]:
    """A run context as data for another run, as deepagents forwards it: without its parent
    reference, and without a choice that came back on a finished task's notification."""
    data = _as_mapping(context) or {}
    return {str(k): v for k, v in data.items() if k not in {_PARENT_KEY, CHOICE_KEY}}


class _StartSchema(StartAsyncTaskSchema):
    # Every task runs on `worker`, so the lead is not shown a type.
    subagent_type: SkipJsonSchema[str] = WORKER
    model: str = Field(
        default="",
        description="The model this helper runs on: any LangChain `provider:model`. Empty for "
        "the default.",
    )
    effort: str = Field(
        default="",
        description="Its reasoning effort: low, medium, high, xhigh or max. Empty for yours.",
    )
    name: str = Field(
        default="",
        description='A short role, 2 to 4 words, like "Meta pull" or "Monthly report". Its '
        "progress notes to you carry it.",
    )


def listing(settings: Settings) -> str:
    """What the lead reads in place of deepagents' agent types."""
    default = settings.paid_media_helper_model or settings.paid_media_model
    return (
        "Every task runs on a read-only helper with your platform reads, compare_periods, "
        "summarize_window and render_report, and no proposals or check-ins. Pick its `model`: "
        f"any LangChain `provider:model` (default {default}); a smaller model suits a plain "
        "pull, and a report a person will read deserves yours. Pick its `effort` (default "
        "yours). Its whole prompt is your `description`: send a complete brief with aliases, "
        "windows, comparison, grain, and what to return. Give it a `name`, a short role."
    )


class AsyncHelpersMiddleware(AgentMiddleware[Any, Any, Any]):
    """The lead's side: `start_async_task` with a model, an effort and a role (module doc)."""

    name = "PaidMediaAsyncHelpers"

    def __init__(self, settings: Settings, choose: Callable[[str, str], HelperChoice | str]):
        super().__init__()
        self._listing = listing(settings)
        self._choose = choose

    async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:  # noqa: ARG002
        """Hand the lead the progress notes its tasks sent since its last model call."""
        store = getattr(runtime, "store", None)
        thread = (get_config().get("configurable") or {}).get("thread_id")
        if store is None or not thread:
            return None
        items = await store.asearch((*NOTES, str(thread)), limit=_NOTES_READ)
        if not items:
            return None
        for item in items:
            await store.adelete(item.namespace, item.key)
        notes = sorted((item.value for item in items), key=lambda note: note.get("at", 0))
        return {"messages": [notes_message(notes)]}

    def _shown(self, tool: Any) -> Any:
        if not isinstance(tool, BaseTool) or tool.name != START:
            return tool
        head, found, rest = (tool.description or "").partition(_TYPES_HEAD)
        _, usage, notes = rest.partition(_USAGE_HEAD)
        text = f"{head}{self._listing}\n\n{usage}{notes}" if found and usage else tool.description
        return tool.model_copy(update={"args_schema": _StartSchema, "description": text})

    def _with_start(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        tools = [self._shown(tool) for tool in request.tools]
        changed = any(new is not old for new, old in zip(tools, request.tools, strict=True))
        return request.override(tools=tools) if changed else request

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(self._with_start(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._with_start(request))

    async def awrap_tool_call(
        self, request: Any, handler: Callable[[Any], Awaitable[Any]]
    ) -> ToolMessage | Command[Any]:
        call = request.tool_call
        name = call.get("name")
        if name == START:
            args = dict(call.get("args") or {})
            picked = self._choose(
                str(args.pop("model", "") or ""), str(args.pop("effort", "") or "")
            )
            if isinstance(picked, str):
                return ToolMessage(picked, tool_call_id=call["id"], name=START, status="error")
            role = " ".join(str(args.pop("name", "") or "").split())[:_NAME_CHARS]
            chosen: dict[str, str] | None = {
                "model": picked.model,
                "effort": picked.effort or "",
                "name": role,
            }
            request = request.override(
                tool_call={**call, "args": {**args, "subagent_type": WORKER}}
            )
        elif name == UPDATE:
            chosen = _chosen_for(request, str((call.get("args") or {}).get("task_id") or ""))
        else:
            result: ToolMessage | Command[Any] = await handler(request)
            return result
        result = await handler(_with_choice(request, chosen))
        return _marked(result, chosen) if name == START and chosen is not None else result


def _with_choice(request: Any, chosen: Mapping[str, str] | None) -> Any:
    """`request` with a runtime whose context is what the task's run gets, plus the choice."""
    runtime = getattr(request, "runtime", None)
    if not dataclasses.is_dataclass(runtime) or isinstance(runtime, type):
        return request
    context = forwarded(getattr(runtime, "context", None))
    if chosen is not None:
        context[CHOICE_KEY] = dict(chosen)
    return request.override(runtime=dataclasses.replace(runtime, context=context or None))


def _chosen_for(request: Any, task_id: str) -> dict[str, str] | None:
    """The choice a task started on, from its record: a follow-up keeps its model."""
    state = getattr(request, "state", None)
    tasks = state.get("async_tasks") if isinstance(state, Mapping) else None
    task = tasks.get(task_id.strip()) if isinstance(tasks, Mapping) else None
    data = _as_mapping(task)
    chosen = data.get(CHOICE_KEY) if data is not None else None
    return dict(chosen) if isinstance(chosen, Mapping) else None


def _marked(result: Any, chosen: Mapping[str, str]) -> Any:
    """The started task's record carrying its choice; deepagents' later updates keep the key."""
    update = getattr(result, "update", None)
    if not isinstance(update, Mapping):
        return result
    tasks = update.get("async_tasks")
    if not isinstance(tasks, Mapping) or len(tasks) != 1:
        return result
    ((task_id, task),) = tasks.items()
    marked = {**task, CHOICE_KEY: dict(chosen)}
    return dataclasses.replace(result, update={**update, "async_tasks": {task_id: marked}})


class _ByChoice(AgentMiddleware[Any, Any, Any]):
    """Base for the worker's per-choice middleware: what the stamp resolves to, or None for the
    default, so the model and the tool selection always agree."""

    def __init__(self, models: HelperModels) -> None:
        super().__init__()
        self._models = models

    def _resolved(self, request: ModelRequest[Any]) -> tuple[HelperChoice, BaseChatModel] | None:
        chosen = stamped(getattr(request.runtime, "context", None))
        return self._models.resolve(chosen) if chosen is not None else None


class WorkerModelMiddleware(_ByChoice):
    """The worker's side: each model call runs on the stamped model and effort (module doc)."""

    name = "PaidMediaWorkerModel"

    def _swapped(self, request: ModelRequest[Any]) -> ModelRequest[Any]:
        resolved = self._resolved(request)
        return request if resolved is None else request.override(model=resolved[1])

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> ModelResponse[Any]:
        return handler(self._swapped(request))

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> ModelResponse[Any]:
        return await handler(self._swapped(request))


SelectionFor = Callable[[HelperChoice | None], Sequence[AgentMiddleware[Any, Any, Any]]]


class WorkerSelectionMiddleware(_ByChoice):
    """Tool selection for the model each call runs on: provider tool search fails on a model
    without it (`middleware/tool_selection.py`), so it is picked per choice."""

    name = "PaidMediaWorkerSelection"

    def __init__(self, selection_for: SelectionFor, models: HelperModels) -> None:
        super().__init__(models)
        self._for = selection_for
        self._made: dict[HelperChoice | None, AgentMiddleware[Any, Any, Any] | None] = {}

    def _pick(self, request: ModelRequest[Any]) -> AgentMiddleware[Any, Any, Any] | None:
        resolved = self._resolved(request)
        chosen = resolved[0] if resolved is not None else None
        if chosen not in self._made:
            made = self._for(chosen)
            self._made[chosen] = made[0] if made else None
        return self._made[chosen]

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], ModelResponse[Any]]
    ) -> Any:
        inner = self._pick(request)
        return handler(request) if inner is None else inner.wrap_model_call(request, handler)

    async def awrap_model_call(
        self,
        request: ModelRequest[Any],
        handler: Callable[[ModelRequest[Any]], Awaitable[ModelResponse[Any]]],
    ) -> Any:
        inner = self._pick(request)
        if inner is None:
            return await handler(request)
        return await inner.awrap_model_call(request, handler)


def notes_message(notes: Sequence[Mapping[str, Any]]) -> HumanMessage:
    """Progress notes as one message to the lead, marked as not from a person."""
    lines = "\n".join(
        f"- {note.get('task', '?')}{' (urgent)' if note.get('urgent') else ''}: {note.get('note')}"
        for note in notes
    )
    return HumanMessage(
        "<helper-notes>\nProgress notes from your background helpers, not from a person:\n"
        f"{lines}\n</helper-notes>",
        additional_kwargs={NOTES_KEY: True},
    )


def lead_thread(config: Mapping[str, Any]) -> str | None:
    """The lead's thread: the task thread's metadata (`parent_thread_id`), which the Agent Server
    copies into every run on it, or deepagents' parent reference when a run has no context."""
    reference = (config.get("configurable") or {}).get(_PARENT_KEY)
    thread = reference.get("thread_id") if isinstance(reference, Mapping) else None
    thread = thread or (config.get("metadata") or {}).get("parent_thread_id")
    return str(thread) if thread else None


def _lead_assistant(config: Mapping[str, Any]) -> str | None:
    reference = (config.get("configurable") or {}).get(_PARENT_KEY)
    assistant = reference.get("assistant_id") if isinstance(reference, Mapping) else None
    assistant = assistant or (config.get("metadata") or {}).get("parent_assistant_id")
    return str(assistant) if assistant else None


async def _wake_lead(config: Mapping[str, Any], context: object, note: Mapping[str, Any]) -> bool:
    """Start a run on an idle lead's thread with `note`; False when it is busy or out of reach,
    and it then reads the note before its next model call. Never raises."""
    lead, assistant = lead_thread(config), _lead_assistant(config)
    if lead is None or assistant is None:
        return False
    try:
        client = get_client()
        if (await client.threads.get(thread_id=lead)).get("status") not in _WAKEABLE:
            return False
        message = notes_message([note])
        payload: dict[str, Any] = {
            "role": "user",
            "content": message.text,
            "additional_kwargs": dict(message.additional_kwargs),
        }
        body: dict[str, Any] = {"messages": [payload]}
        await client.runs.create(
            lead,
            assistant,
            input=body,
            multitask_strategy="reject",
            context=forwarded(context) or None,
        )
    except Exception as error:
        _LOGGER.info("[worker] lead not woken for an urgent note: %s", type(error).__name__)
        return False
    return True


async def report_progress(note: str, runtime: ToolRuntime, urgent: bool = False) -> str:
    """Tell the lead how this task is going.

    Send one when a part is done, when something blocks you or changes how long you need, and
    before you stop early: one or two sentences on what happened and what comes next. The lead
    reads it before its next step. Set `urgent` only when the lead must decide something; an idle
    lead is then woken for it.
    """
    config = runtime.config or {}
    lead, store = lead_thread(config), runtime.store
    if lead is None or store is None:
        return "This task has no lead to tell; put it in your final summary instead."
    task = helper_label(runtime.context) or "A helper"
    value = {"task": task, "note": note.strip()[:_NOTE_CHARS], "urgent": urgent, "at": time.time()}
    if urgent and await _wake_lead(config, runtime.context, value):
        return "Sent; the lead was woken for it."
    await store.aput((*NOTES, lead), uuid.uuid4().hex, value)
    return "Sent; the lead reads it before its next step."


class WorkerNotesMiddleware(AgentMiddleware[Any, Any, Any]):
    """Gives the worker `report_progress` (module doc)."""

    name = "PaidMediaWorkerNotes"

    def __init__(self) -> None:
        super().__init__()
        self.tools = [
            StructuredTool.from_function(coroutine=report_progress, name=REPORT_PROGRESS_TOOL)
        ]
