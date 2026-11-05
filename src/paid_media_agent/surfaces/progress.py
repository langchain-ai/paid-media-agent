"""What each step is called in Slack: an analyst's phrase per tool call, in both tenses.

A step reads like a paid-media analyst at work ("Reading Google Ads campaign performance",
"Comparing the two periods", "Handing the account pull to a helper") rather than a tool name.
Every phrase is a pair: what the step is doing while it runs, and what it did.

The phrasebook is deterministic and grows without an entry per platform tool:

- **This repository's tools** have an entry each.
- **Platform read tools** (`{platform}__{operation}`) are parsed: the platform becomes its name
  ("Meta Ads") and the operation's verb is put in both tenses.
- **Built-in file tools** are phrased from their path: a skill is its guide, a wiki page is the
  wiki's note on that topic, `/workspace/analysis` is saved analysis.
- **Anything else** is its name, humanized.

A step is shown before anyone reviews it, so a phrase never carries argument text (no account
alias, query, or anybody's words). The only names it shows are this repository's own: a skill's
directory, a wiki page, a helper's type, a platform.

Two surfaces read it. On Managed Deep Agents, `plan_from_state` is the Slack channel's `status`
chooser (`channels/slack.py`): Slack shows the current turn's steps as a plan above the reply.
The self-hosted Slack adapter streams the same phrases as task updates.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

from paid_media_agent.domain.common import Platform

Phrase = tuple[str, str]
StepStatus = Literal["pending", "in_progress", "complete", "error"]

#: Steps a plan shows; older steps of a long turn drop off the top.
MAX_STEPS = 10

PLATFORM_NAMES: Mapping[str, str] = {
    Platform.GOOGLE_ADS: "Google Ads",
    Platform.META_ADS: "Meta Ads",
    Platform.REDDIT_ADS: "Reddit Ads",
    Platform.TIKTOK_ADS: "TikTok Ads",
    Platform.PINTEREST_ADS: "Pinterest Ads",
    Platform.SNAP_ADS: "Snap Ads",
    Platform.GOOGLE_ANALYTICS: "Google Analytics",
    Platform.LINKEDIN_ADS: "LinkedIn Ads",
    Platform.X_ADS: "X Ads",
    Platform.OPENAI_ADS: "OpenAI Ads",
}

#: Helper types (`subagents.py`) as a person would say them.
HELPER_WORK: Mapping[str, str] = {
    "account-puller": "the account pull",
    "report-builder": "the report",
}

TOOL_PHRASES: Mapping[str, Phrase] = {
    "list_accounts": ("Checking connected accounts", "Checked connected accounts"),
    "discover_tools": (
        "Looking up what each platform reports",
        "Looked up what each platform reports",
    ),
    "compare_periods": ("Comparing the two periods", "Compared the two periods"),
    "summarize_window": ("Summarizing the window", "Summarized the window"),
    "render_report": ("Rendering the report", "Rendered the report"),
    "discover_write_operations": (
        "Checking which changes are allowed",
        "Checked which changes are allowed",
    ),
    "propose_change": ("Drafting the change for review", "Drafted the change for review"),
    "execute_change": ("Waiting for approval", "Finished the change review"),
    "get_proposal": ("Checking the proposal", "Checked the proposal"),
    "schedule_check_in": ("Scheduling a check-in", "Scheduled a check-in"),
    "cancel_check_in": ("Cancelling a check-in", "Cancelled a check-in"),
    "write_todos": ("Planning the analysis", "Planned the analysis"),
    "check_async_task": ("Checking on a helper", "Checked on a helper"),
    "list_async_tasks": ("Checking on the helpers", "Checked on the helpers"),
    "update_async_task": ("Updating a helper's brief", "Updated a helper's brief"),
    "cancel_async_task": ("Stopping a helper", "Stopped a helper"),
}

#: An operation's leading verb, in both tenses.
_VERBS: Mapping[str, Phrase] = {
    "get": ("Reading", "Read"),
    "read": ("Reading", "Read"),
    "fetch": ("Fetching", "Fetched"),
    "list": ("Listing", "Listed"),
    "search": ("Searching", "Searched"),
    "query": ("Querying", "Queried"),
    "run": ("Running", "Ran"),
    "describe": ("Describing", "Described"),
}

_WIKI = "paid-media-wiki"
_SKILL_NAMES: Mapping[str, str] = {
    "company-context": "your company context",
    "report-design": "the report design guide",
    "paid-media-analysis": "the analysis playbook",
    "paid-media-report": "the report playbook",
    "paid-media-writes": "the change playbook",
    _WIKI: "the paid-media wiki",
}


def _words(name: str) -> str:
    return re.sub(r"[-_]+", " ", name).strip()


def _humanize(name: str) -> str:
    words = _words(name)
    return words[:1].upper() + words[1:] if words else "Working"


def _place(path: object) -> str:
    """A path as an analyst would name it."""
    raw = str(path or "").strip()
    if not raw:
        return "the workspace"
    norm = posixpath.normpath(raw if raw.startswith("/") else f"/workspace/{raw}")
    skill = re.match(r"^(?:/workspace)?/skills/([^/]+)(?:/(.+))?", norm)
    if skill:
        name, rest = skill.group(1), skill.group(2) or ""
        page = posixpath.splitext(posixpath.basename(rest))[0]
        if name == _WIKI and page and page.upper() != "SKILL":
            return f"the wiki on {_words(page)}"
        return _SKILL_NAMES.get(name, f"the {_words(name)} guide")
    if norm.startswith("/memories/user"):
        return "your preferences"
    if norm.startswith("/memories"):
        return "the team's notes"
    for prefix, name in (
        ("/workspace/analysis", "saved analysis"),
        ("/workspace/out", "a report"),
        ("/workspace/in", "your file"),
        ("/workspace/attachments", "your file"),
    ):
        if norm == prefix or norm.startswith(f"{prefix}/"):
            return name
    return "the workspace" if norm in ("/", "/workspace") else "a file"


def _file_phrase(name: str, args: Mapping[str, object]) -> Phrase | None:
    place = _place(args.get("file_path") or args.get("path"))
    if name == "read_file":
        return f"Reading {place}", f"Read {place}"
    if name in ("ls", "glob", "grep"):
        return f"Looking through {place}", f"Looked through {place}"
    if name == "write_file":
        return f"Saving {place}", f"Saved {place}"
    if name == "edit_file":
        return f"Updating {place}", f"Updated {place}"
    return None


def _platform_phrase(name: str) -> Phrase | None:
    platform, sep, operation = name.partition("__")
    if not sep or platform not in PLATFORM_NAMES or not operation:
        return None
    service = PLATFORM_NAMES[platform]
    verb, _, rest = operation.partition("_")
    tenses = _VERBS.get(verb)
    subject = _words(rest)
    if tenses is None or not subject:
        work = _words(operation)
        return f"Checking {service} {work}", f"Checked {service} {work}"
    return f"{tenses[0]} {service} {subject}", f"{tenses[1]} {service} {subject}"


def phrase(name: str, args: Mapping[str, object] | None = None) -> Phrase:
    """A tool call's step, while it runs and once it is done."""
    args = args or {}
    if name == "start_async_task":
        work = HELPER_WORK.get(str(args.get("subagent_type") or ""))
        if work:
            return f"Handing {work} to a helper", f"Handed {work} to a helper"
        return "Starting a background helper", "Started a background helper"
    known = TOOL_PHRASES.get(name) or _file_phrase(name, args) or _platform_phrase(name)
    if known is not None:
        return known
    humanized = _humanize(name)
    return humanized, humanized


def _field(message: Any, key: str) -> Any:
    return message.get(key) if isinstance(message, Mapping) else getattr(message, key, None)


def _kind(message: Any) -> str:
    kind = _field(message, "type")
    return str(kind) if kind else ""


def plan_steps(messages: Sequence[Any]) -> list[dict[str, str]]:
    """The current turn's tool calls as plan steps: everything after the latest human message.

    A call with a result is `complete` (or `error`); one without is `in_progress`.
    """
    start = 0
    for index in range(len(messages) - 1, -1, -1):
        if _kind(messages[index]) == "human":
            start = index + 1
            break
    turn = messages[start:]
    results: dict[str, StepStatus] = {}
    for message in turn:
        if _kind(message) == "tool":
            call_id = str(_field(message, "tool_call_id") or "")
            results[call_id] = "error" if _field(message, "status") == "error" else "complete"
    steps: list[dict[str, str]] = []
    for message in turn:
        if _kind(message) != "ai":
            continue
        for call in _field(message, "tool_calls") or ():
            if not isinstance(call, Mapping):
                continue
            args = call.get("args")
            running, done = phrase(
                str(call.get("name") or ""), args if isinstance(args, Mapping) else None
            )
            status = results.get(str(call.get("id") or ""), "in_progress")
            steps.append({"title": running if status == "in_progress" else done, "status": status})
    return steps[-MAX_STEPS:]


def plan_from_state(context: Mapping[str, Any]) -> list[dict[str, str]] | None:
    """MDA's Slack `status` chooser: the turn's steps, or None to leave what Slack shows."""
    state = context.get("state")
    messages = state.get("messages") if isinstance(state, Mapping) else None
    if not isinstance(messages, Sequence):
        return None
    return plan_steps(messages) or None
