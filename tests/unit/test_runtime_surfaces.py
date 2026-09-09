"""Regressions caught while running the agent behind LangGraph Server and the self-hosted API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from paid_media_agent.middleware.current_date import CurrentDateMiddleware
from paid_media_agent.middleware.offload import ResultOffloadMiddleware
from paid_media_agent.middleware.timeout import ModelTimeoutMiddleware
from paid_media_agent.surfaces.runner import _content_text, _last_assistant_text
from paid_media_agent.tools.artifacts import ArtifactStore


def test_outcome_text_flattens_content_blocks() -> None:
    """The API returned the Python repr of a block list; only the text may reach a client."""
    blocks = [
        {"type": "text", "text": "demo-google spent the most.", "annotations": [], "id": "m1"},
        {"type": "reasoning", "text": "hidden"},
    ]
    assert _content_text(blocks) == "demo-google spent the most."
    assert _last_assistant_text([AIMessage(content=blocks)]) == "demo-google spent the most."
    assert _content_text("  plain  ") == "plain"


def test_current_date_is_appended_per_model_call() -> None:
    """Relative windows must resolve from today, not from the model's training-time year."""
    middleware = CurrentDateMiddleware(now=lambda: datetime(2026, 9, 2, 12, tzinfo=UTC))
    seen: list[SystemMessage | None] = []

    class Request:
        system_message = SystemMessage(content="Base instructions.")

        def override(self, **overrides):
            seen.append(overrides["system_message"])
            return self

    middleware.wrap_model_call(Request(), lambda request: request)  # type: ignore[arg-type]
    stamped = seen[-1]
    assert stamped is not None
    assert isinstance(stamped.content, str)
    assert stamped.content.startswith("Base instructions.")
    assert "Current date (UTC): 2026-09-02" in stamped.content


def test_offload_leaves_paged_filesystem_tools_alone(tmp_path: Path) -> None:
    """A read_file result over the budget was offloaded into a new artifact, which the model then
    had to read, which was offloaded again."""
    middleware = ResultOffloadMiddleware(ArtifactStore(tmp_path), max_chars=100)
    big = "x" * 500

    class Request:
        tool_call = {"name": "read_file", "id": "call-1", "args": {}}

    kept = middleware.wrap_tool_call(
        Request(), lambda _r: ToolMessage(content=big, tool_call_id="call-1")
    )  # type: ignore[arg-type]
    assert kept.content == big
    Request.tool_call = {"name": "google_ads__get_campaign_performance", "id": "call-2", "args": {}}
    offloaded = middleware.wrap_tool_call(
        Request(), lambda _r: ToolMessage(content=big, tool_call_id="call-2")
    )  # type: ignore[arg-type]
    assert '"offloaded": true' in offloaded.content


def test_model_timeout_turns_a_stalled_call_into_an_error() -> None:
    """A streamed gateway call stalled for 15 minutes without tripping the SDK read timeout."""
    middleware = ModelTimeoutMiddleware(0.05)

    async def stalled(_request: object) -> str:
        await asyncio.sleep(1)
        return "never"

    async def quick(_request: object) -> str:
        return "answer"

    with pytest.raises(TimeoutError, match="exceeded 0 seconds"):
        asyncio.run(middleware.awrap_model_call(object(), stalled))  # type: ignore[arg-type]
    assert asyncio.run(middleware.awrap_model_call(object(), quick)) == "answer"  # type: ignore[arg-type]


def test_slack_answers_fold_markdown_into_mrkdwn() -> None:
    from paid_media_agent.surfaces.slack.blocks import to_mrkdwn

    folded = to_mrkdwn("## What I can do\n\n---\n\n- **Spend** is 10 USD\n\n### Next")
    assert folded == "*What I can do*\n\n- *Spend* is 10 USD\n\n*Next*"
