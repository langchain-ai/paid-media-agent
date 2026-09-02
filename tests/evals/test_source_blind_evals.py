"""Source-blind behavioral checks run with the scripted model through the real graph."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from paid_media_agent.config import Settings
from paid_media_agent.testing.demo_script import DEMO_QUESTION, demo_steps
from paid_media_agent.testing.scripted_model import tool_call_message
from tests.contract.helpers import build_runtime, config


async def test_discovers_instead_of_inventing_and_cites_evidence(
    settings: Settings, project_root: Path
) -> None:
    runtime, _ = build_runtime(settings, project_root, demo_steps())
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": DEMO_QUESTION}]}, config=config()
    )
    tool_calls = [
        tc["name"] for m in state["messages"] if isinstance(m, AIMessage) for tc in m.tool_calls
    ]
    assert tool_calls[0] == "discover_tools", "discover before any platform read"
    assert tool_calls.index("compare_periods") > tool_calls.index(
        "google_ads__get_campaign_performance"
    )
    answer = state["messages"][-1].content
    assert answer.count("art_") >= 4, "the answer cites the analysis and each source artifact"
    assert "not zero" in answer and "incrementality" in answer


async def test_missing_window_reports_instead_of_guessing(
    settings: Settings, project_root: Path
) -> None:
    steps = [
        lambda _m: tool_call_message(
            "google_ads__get_campaign_performance",
            {"account_alias": "demo-google", "start_date": "2026-08-01", "end_date": "2026-08-28"},
        ),
        lambda m: tool_call_message(
            "compare_periods",
            {
                "artifact_ids": [
                    json.loads(next(x for x in reversed(m) if isinstance(x, ToolMessage)).content)[
                        "artifact_id"
                    ]
                ],
                "current_start": "2026-08-15",
                "current_end": "2026-08-28",
                "previous_start": "2026-08-01",
                "previous_end": "2026-08-10",
            },
        ),
        lambda m: AIMessage(
            content=str(
                json.loads(next(x for x in reversed(m) if isinstance(x, ToolMessage)).content)
            )
        ),
    ]
    runtime, _ = build_runtime(settings, project_root, steps)
    state = await runtime.graph.ainvoke(
        {"messages": [{"role": "user", "content": "compare"}]}, config=config()
    )
    assert "same day count" in state["messages"][-1].content
