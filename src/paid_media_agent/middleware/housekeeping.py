"""The housekeeping run: tidy in code and end before any model call.

`schedules/housekeeping.py` starts a run once a day whose whole prompt is `<housekeeping>`. This
middleware, first in the list, recognizes it in `before_agent`, deletes the agent's expired
check-ins (one-time schedules the agent made with `schedule_check_in`; they no longer count
against MDA's per-owner cap but would otherwise pile up in listings), and ends the run with a
one-line summary that no channel receives. It never touches a schedule it did not make, and it
reads no account and calls no provider. Any run whose whole message is the marker gets the same,
which is harmless; a marker typed in Slack arrives escaped and decorated, so it reaches the model.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from paid_media_agent.tools.check_ins import METADATA_KEY

_LOGGER = logging.getLogger(__name__)

MARK = "<housekeeping>"
_PAGE = 100


async def tidy_check_ins(schedules: Any) -> int:
    """Delete this agent's expired check-ins; returns how many.

    Every page is read before anything is deleted: the listing's offsets count the server's rows,
    so deleting while paging would skip one row per deletion.
    """
    owner = {"type": "agent"}
    expired: list[str] = []
    offset = 0
    while True:
        page = await schedules.list(owner=owner, limit=_PAGE, offset=offset, include_expired=True)
        expired += [
            str(record["id"])
            for record in page.get("items", [])
            if record.get("expired") and METADATA_KEY in (record.get("metadata") or {})
        ]
        offset = page.get("next_offset") or 0
        if not offset:
            break
    removed = 0
    for schedule_id in expired:
        try:
            await schedules.delete(schedule_id, owner=owner)
            removed += 1
        except Exception as error:  # tomorrow's pass tries again
            _LOGGER.warning("[housekeeping] check-in not deleted: %s", type(error).__name__)
    return removed


def _latest_human_text(state: AgentState[Any]) -> str:
    for message in reversed(state.get("messages") or []):
        if isinstance(message, HumanMessage):
            return message.content.strip() if isinstance(message.content, str) else ""
    return ""


class HousekeepingMiddleware(AgentMiddleware[AgentState[Any], Any, Any]):
    """Recognize the housekeeping run and do it in code (module doc)."""

    name = "PaidMediaHousekeeping"

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        if _latest_human_text(state) != MARK:
            return None
        tidied = 0
        schedules = getattr(runtime, "schedules", None)
        if schedules is not None:
            try:
                tidied = await tidy_check_ins(schedules)
            except Exception as error:  # tomorrow's pass tries again
                _LOGGER.warning("[housekeeping] check-ins not tidied: %s", type(error).__name__)
        summary = f"Housekeeping: {tidied} expired check-in(s) removed."
        return {"messages": [AIMessage(content=summary)], "jump_to": "end"}
