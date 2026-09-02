"""Regressions caught while running the agent behind LangGraph Server and the self-hosted API."""

from __future__ import annotations

from datetime import UTC, datetime

from langchain_core.messages import AIMessage, SystemMessage

from paid_media_agent.middleware.current_date import CurrentDateMiddleware
from paid_media_agent.surfaces.runner import _content_text, _last_assistant_text


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

        def override(self, **overrides):  # noqa: ANN003, ANN202 - test double
            seen.append(overrides["system_message"])
            return self

    middleware.wrap_model_call(Request(), lambda request: request)  # type: ignore[arg-type]
    stamped = seen[-1]
    assert stamped is not None
    assert isinstance(stamped.content, str)
    assert stamped.content.startswith("Base instructions.")
    assert "Current date (UTC): 2026-09-02" in stamped.content
