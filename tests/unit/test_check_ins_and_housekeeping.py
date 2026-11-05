"""Check-ins on MDA runtime schedules, and the housekeeping run that tidies them in code."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from paid_media_agent.config import Settings
from paid_media_agent.middleware.housekeeping import MARK, tidy_check_ins
from paid_media_agent.tools.check_ins import METADATA_KEY, build_check_in_tools
from tests.contract.helpers import build_runtime, config


class FakeSchedules:
    """`runtime.schedules` with MDA's record shape; never reaches a network."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = {r["id"]: r for r in records or []}
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []

    async def create(self, **kwargs: Any) -> dict[str, Any]:
        self.created.append(kwargs)
        record = {
            "id": f"s{len(self.created)}",
            "owner": kwargs["owner"],
            "at": kwargs["at"].isoformat(),
            "thread": {"mode": "persistent", "id": "thread-1"},
            "metadata": kwargs["metadata"],
            "expired": False,
        }
        self.records[record["id"]] = record
        return record

    async def get(self, id: str, *, owner: dict[str, str]) -> dict[str, Any]:
        return self.records[id]

    async def list(self, *, owner: dict[str, str], **_: Any) -> dict[str, Any]:
        return {"items": list(self.records.values()), "next_offset": None}

    async def delete(self, id: str, *, owner: dict[str, str]) -> None:
        self.deleted.append(id)
        self.records.pop(id)


def _tools() -> dict[str, Any]:
    return {tool.name: tool.coroutine for tool in build_check_in_tools()}


def _runtime(schedules: FakeSchedules | None, *, channel: bool = True) -> SimpleNamespace:
    origin = SimpleNamespace(channel=SimpleNamespace(provider="slack")) if channel else None
    return SimpleNamespace(
        schedules=schedules,
        thread=SimpleNamespace(id="thread-1", origin=origin),
        config={"configurable": {"thread_id": "thread-1"}},
    )


async def test_check_in_is_a_one_time_schedule_on_this_thread() -> None:
    schedules = FakeSchedules()
    result = json.loads(
        await _tools()["schedule_check_in"](
            delay_minutes=2880,
            note="acme-search budget change: compare CPA",
            runtime=_runtime(schedules),
        )
    )
    assert result["check_in_id"] == "s1"
    created = schedules.created[0]
    assert created["owner"] == {"type": "agent"}, "a channel thread's check-in belongs to the agent"
    assert created["new_thread"] is False and created["metadata"] == {METADATA_KEY: "check-in"}
    assert "acme-search budget change" in created["prompt"]
    assert "propose any change for approval" in created["prompt"]
    await _tools()["schedule_check_in"](
        delay_minutes=60, note="x", runtime=_runtime(schedules, channel=False)
    )
    assert schedules.created[1]["owner"] == {"type": "user"}


async def test_check_ins_need_runtime_schedules() -> None:
    result = json.loads(
        await _tools()["schedule_check_in"](delay_minutes=60, note="x", runtime=_runtime(None))
    )
    assert result["error"] == "check_ins_unavailable"


async def test_cancel_reaches_only_this_threads_check_ins() -> None:
    operator = {
        "id": "weekly",
        "metadata": {},
        "thread": {"mode": "persistent", "id": "thread-1"},
        "expired": False,
    }
    elsewhere = {
        "id": "other",
        "metadata": {METADATA_KEY: "check-in"},
        "thread": {"mode": "persistent", "id": "thread-2"},
        "expired": False,
    }
    schedules = FakeSchedules([operator, elsewhere])
    cancel = _tools()["cancel_check_in"]
    for refused in ("weekly", "other", "missing"):
        result = json.loads(await cancel(check_in_id=refused, runtime=_runtime(schedules)))
        assert result["error"] == "unknown_check_in"
    created = json.loads(
        await _tools()["schedule_check_in"](delay_minutes=60, note="x", runtime=_runtime(schedules))
    )
    result = json.loads(await cancel(check_in_id="missing", runtime=_runtime(schedules)))
    assert [p["check_in_id"] for p in result["pending_check_ins"]] == [created["check_in_id"]]
    result = json.loads(
        await cancel(check_in_id=created["check_in_id"], runtime=_runtime(schedules))
    )
    assert result == {"cancelled": created["check_in_id"]}
    assert schedules.deleted == [created["check_in_id"]]


async def test_housekeeping_tidies_only_expired_check_ins() -> None:
    schedules = FakeSchedules(
        [
            {"id": "old", "metadata": {METADATA_KEY: "check-in"}, "expired": True},
            {"id": "due", "metadata": {METADATA_KEY: "check-in"}, "expired": False},
            {"id": "operator", "metadata": {}, "expired": True},
        ]
    )
    assert await tidy_check_ins(schedules) == 1
    assert schedules.deleted == ["old"]


async def test_housekeeping_run_ends_in_code_without_a_model_call(
    settings: Settings, project_root: Path
) -> None:
    def never(_messages: Any) -> AIMessage:
        raise AssertionError("housekeeping must not call the model")

    runtime, model = build_runtime(settings, project_root, [never])
    state = await runtime.graph.ainvoke({"messages": [HumanMessage(MARK)]}, config("hk"))
    assert model.call_count == 0
    assert state["messages"][-1].content == "Housekeeping: 0 expired check-in(s) removed."
