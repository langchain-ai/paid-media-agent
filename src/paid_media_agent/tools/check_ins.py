"""Check-ins: the agent comes back to this conversation later, on MDA runtime schedules.

A paid-media change takes days to show in the numbers. After an approved budget change, or when a
person asks "tell me Thursday whether CPA recovered", the agent sets a check-in: a one-time
schedule on this thread (`runtime.schedules.create(at=..., new_thread=False)`). It survives
redeploys, and its run answers in the conversation it came from. The note is the agent's own
brief to its future self.

A check-in is owned by the agent when the thread came from a channel (MDA requires a channel for
an agent-owned same-thread schedule) and by the person otherwise. Its run is an ordinary run: it
reads with the same tools, and any change it suggests still needs a person's approval. Cancelling
reaches only this conversation's check-ins, never another schedule.

Only Managed Deep Agents has durable runtime schedules, so only its assembly binds these tools.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from paid_media_agent.middleware.meter import run_thread
from paid_media_agent.middleware.redaction import sanitize_exception

SCHEDULE_CHECK_IN_TOOL = "schedule_check_in"
CANCEL_CHECK_IN_TOOL = "cancel_check_in"
CHECK_IN_TOOLS: tuple[str, ...] = (SCHEDULE_CHECK_IN_TOOL, CANCEL_CHECK_IN_TOOL)
#: Metadata on every schedule this agent makes, so housekeeping and cancel touch only those.
METADATA_KEY = "paid_media_agent"
MIN_MINUTES = 5
MAX_MINUTES = 30 * 24 * 60


class ScheduleCheckInArgs(BaseModel):
    delay_minutes: int = Field(
        ge=MIN_MINUTES,
        le=MAX_MINUTES,
        description=(
            "Minutes from now. A budget, bid, or status change needs a day or two of data before "
            "it reads: 1440 is one day, 4320 three days."
        ),
    )
    note: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Your brief to your future self: the account alias, what changed or what to watch, "
            "and the window to compare. No credentials or provider ids."
        ),
    )


class CancelCheckInArgs(BaseModel):
    check_in_id: str = Field(description="The id schedule_check_in returned.")


def _owner(runtime: Any) -> dict[str, str]:
    origin = getattr(getattr(runtime, "thread", None), "origin", None)
    return {"type": "agent"} if origin is not None else {"type": "user"}


def _thread(runtime: Any) -> str:
    thread = getattr(getattr(runtime, "thread", None), "id", None)
    if thread:
        return str(thread)
    config = getattr(runtime, "config", None) or {}
    return str((config.get("configurable") or {}).get("thread_id") or run_thread())


def _mine(record: Any, thread_id: str) -> bool:
    if not isinstance(record, dict):
        return False
    target = record.get("thread") or {}
    return (
        METADATA_KEY in (record.get("metadata") or {})
        and isinstance(target, dict)
        and str(target.get("id") or "") == thread_id
    )


def _unavailable() -> str:
    return json.dumps(
        {"error": "check_ins_unavailable", "detail": "This run has no runtime schedules."}
    )


async def _pending(schedules: Any, owner: dict[str, str], thread_id: str) -> list[dict[str, Any]]:
    page = await schedules.list(owner=owner, limit=50)
    return [
        {"check_in_id": record["id"], "due_at": record.get("at", "")}
        for record in page.get("items", [])
        if _mine(record, thread_id)
    ]


def build_check_in_tools() -> list[BaseTool]:
    async def _schedule(delay_minutes: int, note: str, runtime: ToolRuntime) -> str:
        schedules = getattr(runtime, "schedules", None)
        if schedules is None:
            return _unavailable()
        now = datetime.now(UTC)
        due = now + timedelta(minutes=delay_minutes)
        prompt = (
            f"Check-in you scheduled on {now:%Y-%m-%d %H:%M} UTC: {note.strip()}\n\n"
            "Read what you need, report what changed in a few lines with the source window, and "
            "propose any change for approval as usual."
        )
        try:
            record = await schedules.create(
                owner=_owner(runtime),
                at=due,
                prompt=prompt,
                new_thread=False,
                metadata={METADATA_KEY: "check-in"},
            )
        except Exception as error:  # the model reports why and carries on
            return json.dumps(
                {"error": "check_in_not_scheduled", "detail": sanitize_exception(error)[:240]}
            )
        return json.dumps(
            {
                "check_in_id": record["id"],
                "due_at": due.isoformat(timespec="minutes"),
                "note": "The check-in answers in this conversation. Tell the person when it is due.",
            }
        )

    async def _cancel(check_in_id: str, runtime: ToolRuntime) -> str:
        schedules = getattr(runtime, "schedules", None)
        if schedules is None:
            return _unavailable()
        owner, thread_id = _owner(runtime), _thread(runtime)
        try:
            record = await schedules.get(check_in_id, owner=owner)
        except Exception:  # unknown, not ours, or gone: all read as unknown
            record = None
        if not _mine(record, thread_id):
            try:
                pending = await _pending(schedules, owner, thread_id)
            except Exception:  # the refusal stands without the list
                pending = []
            return json.dumps(
                {"error": "unknown_check_in", "pending_check_ins": pending}, default=str
            )
        try:
            await schedules.delete(check_in_id, owner=owner)
        except Exception as error:  # the model reports why
            return json.dumps(
                {"error": "check_in_not_cancelled", "detail": sanitize_exception(error)[:240]}
            )
        return json.dumps({"cancelled": check_in_id})

    return [
        StructuredTool.from_function(
            coroutine=_schedule,
            name=SCHEDULE_CHECK_IN_TOOL,
            description=(
                "Come back to this conversation later with a note for yourself, for example to "
                "check whether an approved change worked or to report when data is complete. "
                "The check-in answers here. It cannot make changes on its own."
            ),
            args_schema=ScheduleCheckInArgs,
        ),
        StructuredTool.from_function(
            coroutine=_cancel,
            name=CANCEL_CHECK_IN_TOOL,
            description="Cancel a check-in this conversation scheduled. An unknown id lists the pending ones.",
            args_schema=CancelCheckInArgs,
        ),
    ]
