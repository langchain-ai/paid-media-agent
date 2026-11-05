"""A footer line under the agent's Slack replies: helpers running, minutes, approximate cost.

While helpers work in the background the line reads `_1 helper running · 3 min · ~$0.12 so far_`;
under the reply that closes the job it settles to `_2 helpers · 6 min · ~$0.41_`. A job is a
person's latest request (`Meter.start_job`), so the wake-up runs that report a finished helper
keep counting the request that started it. Cost is the meter's estimate for the lead and its
helpers; a model the price table does not list shows no cost rather than a wrong one.

The line is part of the reply itself, not a message of its own: Managed Deep Agents posts the
run's last answer, and a second message would be a second notification. It is added only to
Slack replies (`runtime.thread.origin` on MDA, `surface` in the self-hosted Slack run's config),
only to a turn that did work (a tool call or a helper), never to an exact `[quiet]`, and the
model never sees it: footers are cut from earlier replies before each model call.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.config import get_config

from paid_media_agent.middleware.housekeeping import MARK
from paid_media_agent.middleware.meter import Meter

_LOGGER = logging.getLogger(__name__)

#: Where a reply keeps its footer, so it can be cut before the model reads the reply again.
FOOTER_KEY = "paid_media_footer"
#: The task-notification marker deepagents puts on the message that wakes a lead.
NOTIFICATION_KEY = "deepagents_notification"
QUIET = "[quiet]"
_RUNNING = frozenset({"pending", "running"})


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def footer_line(*, minutes: float, usd: float | None, running: int = 0, helpers: int = 0) -> str:
    """The footer in Slack markdown. `usd` is None when the estimate is incomplete."""
    parts: list[str] = []
    if running:
        parts.append(f"{_count(running, 'helper')} running")
    elif helpers:
        parts.append(_count(helpers, "helper"))
    parts.append("<1 min" if minutes < 1 else f"{round(minutes)} min")
    if usd is not None:
        parts.append(f"~${max(usd, 0.0):,.2f}" + (" so far" if running else ""))
    return "_" + " · ".join(parts) + "_"


def slack_run(runtime: Any) -> bool:
    """Whether this run's answer goes to Slack.

    On Managed Deep Agents the thread's origin says so, set by managed ingress and never by a
    caller. The self-hosted Slack adapter marks its runs with `surface` in their config.
    """
    origin = getattr(getattr(runtime, "thread", None), "origin", None)
    channel = getattr(origin, "channel", None)
    if channel is not None:
        return getattr(channel, "provider", None) == "slack"
    try:
        configurable = get_config().get("configurable") or {}
    except RuntimeError:
        return False
    return configurable.get("surface") == "slack"


def person_turn(messages: Sequence[BaseMessage]) -> bool:
    """Whether the run was started by a person, not a helper's notification or housekeeping."""
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return NOTIFICATION_KEY not in message.additional_kwargs and (
                not isinstance(message.content, str) or message.content.strip() != MARK
            )
    return False


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, Mapping) and block.get("type") == "text"
        )
    return ""


def _with_footer(message: AIMessage, line: str) -> AIMessage:
    content = message.content
    if isinstance(content, str):
        updated: Any = f"{content.rstrip()}\n\n{line}"
    else:
        updated = [*content, {"type": "text", "text": f"\n\n{line}"}]
    return message.model_copy(
        update={
            "content": updated,
            "additional_kwargs": {**message.additional_kwargs, FOOTER_KEY: line},
        }
    )


def without_footer[M: BaseMessage](message: M) -> M:
    """The reply as the model wrote it."""
    line = message.additional_kwargs.get(FOOTER_KEY)
    if not isinstance(message, AIMessage) or not isinstance(line, str):
        return message
    content = message.content
    if isinstance(content, str):
        updated: Any = content.removesuffix(f"\n\n{line}")
    else:
        updated = list(content)
        if (
            updated
            and isinstance(updated[-1], Mapping)
            and updated[-1].get("text") == f"\n\n{line}"
        ):
            updated.pop()
    kwargs = {k: v for k, v in message.additional_kwargs.items() if k != FOOTER_KEY}
    return message.model_copy(update={"content": updated, "additional_kwargs": kwargs})


def _turn(messages: Sequence[BaseMessage]) -> Sequence[BaseMessage]:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return messages[index + 1 :]
    return messages


def _since(value: object, started: float) -> bool:
    if not isinstance(value, str):
        return False
    try:
        created = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return False
    return created.timestamp() >= started - 1


class RunFooterMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    """Start a job on a person's request; add the footer to the reply that ends a Slack turn."""

    name = "PaidMediaRunFooter"

    def __init__(self, meter: Meter) -> None:
        super().__init__()
        self._meter = meter

    async def abefore_agent(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        if person_turn(list(state.get("messages") or [])):
            try:
                await self._meter.start_job(runtime)
            except Exception as error:  # the footer is presentation only
                _LOGGER.warning("[footer] job not started: %s", type(error).__name__)
        return None

    async def aafter_agent(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        try:
            return await self._footer(state, runtime)
        except Exception as error:  # the footer is presentation only
            _LOGGER.warning("[footer] not added: %s", type(error).__name__)
            return None

    async def _footer(self, state: AgentState[Any], runtime: Any) -> dict[str, Any] | None:
        messages = list(state.get("messages") or [])
        last = messages[-1] if messages else None
        if (
            not isinstance(last, AIMessage)
            or last.tool_calls
            or FOOTER_KEY in last.additional_kwargs
            or not _text(last.content).strip()
            or _text(last.content).strip() == QUIET
            or not slack_run(runtime)
        ):
            return None
        job = await self._meter.job(runtime)
        if job is None:
            return None
        found = state.get("async_tasks")
        tracked = found.values() if isinstance(found, Mapping) else ()
        tasks = [t for t in tracked if isinstance(t, Mapping)]
        running = sum(1 for t in tasks if t.get("status") in _RUNNING)
        helpers = sum(1 for t in tasks if _since(t.get("created_at"), job.started))
        worked = helpers or any(isinstance(m, ToolMessage) for m in _turn(messages))
        if not worked:
            return None
        totals = await self._meter.totals(runtime)
        usd = None if totals.unpriced > job.base.unpriced else totals.usd - job.base.usd
        line = footer_line(
            minutes=(self._meter.clock() - job.started) / 60,
            usd=usd,
            running=running,
            helpers=helpers,
        )
        return {"messages": [_with_footer(last, line)]}

    @staticmethod
    def _strip(request: ModelRequest[Any]) -> ModelRequest[Any]:
        if not any(FOOTER_KEY in m.additional_kwargs for m in request.messages):
            return request
        return request.override(messages=[without_footer(m) for m in request.messages])

    def wrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return handler(self._strip(request))

    async def awrap_model_call(
        self, request: ModelRequest[Any], handler: Callable[[ModelRequest[Any]], Any]
    ) -> Any:
        return await handler(self._strip(request))
