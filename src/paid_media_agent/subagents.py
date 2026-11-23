"""Background helpers: async subagents Managed Deep Agents runs as graphs of their own.

A pull across many accounts or a long window, or a full report render, can take minutes. The lead
hands it to a helper with `start_async_task`, picking the helper's model and effort for that task
(`middleware/async_helpers.py`), tells the person in a line, and ends its turn. MDA runs the
helper on the same deployment, in the lead's sandbox and trace; when it finishes, deepagents wakes
the lead on its thread (`notify_parent`), and MDA posts that run's answer to the Slack thread the
request came from. A helper's run is an Agent Server run of its own, so it survives the lead's
turn ending and is checkpointed like any thread.

Every task runs on `worker`. `general-purpose` is declared too, with the same read-only tools:
without it MDA would add a background copy of the default general-purpose subagent with every tool
the lead has and none of its middleware. The lead never starts it.

Every helper is read-only, by construction rather than by prompt:

- Its tools are listed here: account and catalog discovery, platform reads, the deterministic
  comparisons, and `render_report`. No proposal, execution, check-in, or async-task tool reaches a
  helper.
- Its middleware is its own, because an async subagent does not inherit the lead's: the same
  invocation guard, offload, redaction, retry, and call limit the lead runs with.

Only MDA has an Agent Server to launch these graphs on. Local and self-hosted runs keep the lead
doing the work in its own turn; `task` stays hidden there as everywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

WORKER = "worker"
GENERAL_PURPOSE = "general-purpose"
HELPER_NAMES: tuple[str, ...] = (WORKER, GENERAL_PURPOSE)

#: The tools deepagents' async-subagent middleware gives the lead on MDA.
ASYNC_TASK_TOOLS: tuple[str, ...] = (
    "start_async_task",
    "check_async_task",
    "update_async_task",
    "cancel_async_task",
    "list_async_tasks",
)
#: Helpers read the skills and the workspace; they write results through the artifact tools.
HELPER_FILESYSTEM_TOOLS: tuple[str, ...] = ("ls", "read_file", "glob", "grep")
#: A helper's note to its lead (`middleware/async_helpers.py`).
REPORT_PROGRESS_TOOL = "report_progress"

_DESCRIPTION = (
    "Read-only paid-media work in the background: pulls and comparisons across many accounts or a "
    "long window, a full rendered report, or other research that takes more than a few tool calls. "
    "Returns a compact summary with artifact ids and report files."
)
_PROMPT = (
    "You work in the background for a lead paid-media analyst, on a brief it wrote for you. Read "
    "the relevant skill under /skills/ first. For a report, read /skills/paid-media-report/SKILL.md "
    "and /skills/report-design/SKILL.md, pull the windows the brief names, call compare_periods, "
    "then render_report with a short executive summary. Use account aliases from list_accounts and "
    "discover_tools before assuming a read tool exists. Let compare_periods and summarize_window "
    "compute every metric; quote their numbers and currency codes as returned. Missing data is not "
    "zero, and never publish a cross-platform total unless windows, units, currency, and coverage "
    "match. Keep unavailable platforms visible. Send report_progress when a part is done, when "
    "something blocks you or changes how long you need, and before you stop early; mark it urgent "
    "only when the lead must decide something. Finish with a compact summary the lead can use "
    "directly: accounts and windows covered, the key movements with their numbers, missing or "
    "conflicting data, and the report files or artifact ids. You cannot propose or make changes; "
    "if the brief asks for one, say what you found and leave the change to the lead."
)

MiddlewareFor = Callable[[Sequence[BaseTool]], list[AgentMiddleware[Any, Any, Any]]]


def helper_specs(
    *, tools: Sequence[BaseTool], middleware: MiddlewareFor
) -> dict[str, dict[str, Any]]:
    """Each helper's subagent spec, without `name` and `"async"`: `agent.py` writes those as
    literals after the spread, so `mda build` can read them without running this code."""
    return {
        name: {
            "description": _DESCRIPTION,
            "system_prompt": _PROMPT,
            "tools": list(tools),
            "middleware": middleware(tools),
            "skills": ["/skills/"],
        }
        for name in HELPER_NAMES
    }
