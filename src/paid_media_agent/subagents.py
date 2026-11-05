"""Background helpers: async subagents Managed Deep Agents runs as graphs of their own.

A pull across many accounts or a long window, or a full report render, can take minutes. The lead
hands it to a helper with `start_async_task`, tells the person in a line, and ends its turn. MDA
runs the helper on the same deployment, in the lead's sandbox and trace; when it finishes,
deepagents wakes the lead on its thread (`notify_parent`), and MDA posts that run's answer to the
Slack thread the request came from. A helper's run is an Agent Server run of its own, so it
survives the lead's turn ending and is checkpointed like any thread.

Every helper is read-only, by construction rather than by prompt:

- Its tools are listed here: account and catalog discovery, platform reads, the deterministic
  comparisons, and (for the report helpers) `render_report`. No proposal, execution, check-in, or
  async-task tool reaches a helper.
- Its middleware is its own, because an async subagent does not inherit the lead's: the same
  invocation guard, offload, redaction, retry, and call limit the lead runs with.
- `general-purpose` is declared too. Without it MDA would add a background copy of the default
  general-purpose subagent with every tool the lead has and none of its middleware.

Only MDA has an Agent Server to launch these graphs on. Local and self-hosted runs keep the lead
doing the work in its own turn; `task` stays hidden there as everywhere.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

ACCOUNT_PULLER = "account-puller"
REPORT_BUILDER = "report-builder"
GENERAL_PURPOSE = "general-purpose"
HELPER_NAMES: tuple[str, ...] = (ACCOUNT_PULLER, REPORT_BUILDER, GENERAL_PURPOSE)

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

_READ_ONLY = (
    "You cannot propose or make changes; if the brief asks for one, say what you found and leave "
    "the change to the lead."
)
_RULES = (
    "Use account aliases from list_accounts and discover_tools before assuming a read tool exists. "
    "Let compare_periods and summarize_window compute every metric; quote their numbers and "
    "currency codes as returned. Missing data is not zero, and never publish a cross-platform "
    "total unless windows, units, currency, and coverage match. Keep unavailable platforms visible."
)

_DESCRIPTIONS: Mapping[str, str] = {
    ACCOUNT_PULLER: (
        "Pulls and compares performance across many accounts or a long date window in the "
        "background, and returns a compact summary with artifact ids. Read-only."
    ),
    REPORT_BUILDER: (
        "Builds a full paid-media report in the background: pulls what it needs, compares the "
        "periods, and renders HTML and PDF. Returns the files and a short summary. Read-only."
    ),
    GENERAL_PURPOSE: (
        "Any other read-only paid-media research that would take more than a few tool calls, in "
        "the background. Returns a compact summary."
    ),
}

_PROMPTS: Mapping[str, str] = {
    ACCOUNT_PULLER: (
        "You pull paid-media performance in the background for a lead analyst. Read the accounts "
        "and windows in your brief, then compare or summarize them. "
        f"{_RULES} Finish with a compact summary: accounts and windows covered, the key movements "
        "with their numbers, missing or conflicting data, and the artifact ids the lead can reuse. "
        f"{_READ_ONLY}"
    ),
    REPORT_BUILDER: (
        "You build a paid-media report in the background for a lead analyst. Read "
        "/skills/paid-media-report/SKILL.md and /skills/report-design/SKILL.md first, pull the "
        "windows the brief names, call compare_periods, then render_report with a short executive "
        f"summary. {_RULES} Finish with the report files, the summary in three to five lines, and "
        f"any gaps. {_READ_ONLY}"
    ),
    GENERAL_PURPOSE: (
        "You do read-only paid-media research in the background for a lead analyst. Read the "
        f"relevant skill under /skills/ first. {_RULES} Finish with a compact summary the lead can "
        f"use directly, with the source windows and artifact ids. {_READ_ONLY}"
    ),
}

MiddlewareFor = Callable[[Sequence[BaseTool]], list[AgentMiddleware[Any, Any, Any]]]


def helper_specs(
    *, analysis_tools: Sequence[BaseTool], render_tool: BaseTool, middleware: MiddlewareFor
) -> dict[str, dict[str, Any]]:
    """Each helper's subagent spec, without `name` and `"async"`: `agent.py` writes those as
    literals after the spread, so `mda build` can read them without running this code."""
    reporting = (*analysis_tools, render_tool)
    specs: dict[str, dict[str, Any]] = {}
    for name, tools in (
        (ACCOUNT_PULLER, tuple(analysis_tools)),
        (REPORT_BUILDER, reporting),
        (GENERAL_PURPOSE, reporting),
    ):
        specs[name] = {
            "description": _DESCRIPTIONS[name],
            "system_prompt": _PROMPTS[name],
            "tools": list(tools),
            "middleware": middleware(tools),
            "skills": ["/skills/"],
        }
    return specs
