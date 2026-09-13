from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from paid_media_agent.surfaces.runner import RunEvent, RunOutcome
from paid_media_agent.surfaces.slack.blocks import render_answer
from paid_media_agent.surfaces.slack.delivery import SlackDelivery, deliver
from paid_media_agent.surfaces.slack.service import SlackReply


async def test_native_stream_preserves_text_and_generic_tool_progress() -> None:
    stream = SimpleNamespace(append=AsyncMock(), stop=AsyncMock())
    client = SimpleNamespace(
        agents_sessions_setStatus=AsyncMock(),
        chat_stream=lambda **_kwargs: stream,
        chat_postMessage=AsyncMock(),
    )
    delivery = SlackDelivery(client, channel="C1", thread_ts="1", team="T1", user="U1")
    await delivery.event(RunEvent("start"))
    await delivery.event(RunEvent("tool", id="call-1", name="custom_warehouse_tool"))
    await delivery.event(
        RunEvent("tool", id="call-1", name="custom_warehouse_tool", status="complete")
    )
    await delivery.event(RunEvent("text", text="**Spend** ", id="message-1"))
    await delivery.event(RunEvent("text", text="fell 10%.", id="message-1"))
    outcome = RunOutcome("thread", "**Spend** fell 10%.", False, None, None)
    await delivery.finish(SlackReply("C1", "1", render_answer(outcome.text), outcome))
    client.agents_sessions_setStatus.assert_awaited_once_with(
        channel_id="C1",
        thread_ts="1",
        initiator_user_id="U1",
        status="processing",
    )
    chunks = [
        call.kwargs["chunks"][0].to_dict()
        for call in stream.append.await_args_list
        if "chunks" in call.kwargs
    ]
    assert chunks == [
        {
            "type": "task_update",
            "id": "call-1",
            "title": "custom warehouse tool",
            "status": "in_progress",
        },
        {
            "type": "task_update",
            "id": "call-1",
            "title": "custom warehouse tool",
            "status": "complete",
        },
    ]
    assert (
        "".join(call.kwargs.get("markdown_text", "") for call in stream.append.await_args_list)
        == outcome.text
    )
    stream.stop.assert_awaited_once_with(
        markdown_text="", blocks=None, chunks=None, session_status="active"
    )
    client.chat_postMessage.assert_not_called()


async def test_failed_run_closes_stream_and_clears_processing_status() -> None:
    stream = SimpleNamespace(
        append=AsyncMock(), stop=AsyncMock(side_effect=RuntimeError("stream unavailable"))
    )
    client = SimpleNamespace(
        agents_sessions_setStatus=AsyncMock(),
        chat_stream=lambda **_kwargs: stream,
        chat_postMessage=AsyncMock(),
    )

    async def fail(_body, *, on_event):
        await on_event(RunEvent("start"))
        await on_event(RunEvent("text", text="Partial answer", id="message-1"))
        raise RuntimeError("model unavailable")

    service = SimpleNamespace(handle_event=fail)
    await deliver(
        service,
        client,
        {
            "team_id": "T1",
            "event": {"channel": "C1", "ts": "1", "user": "U1"},
        },
    )
    stream.stop.assert_awaited_once()
    assert "could not finish" in stream.stop.await_args.kwargs["markdown_text"]
    assert client.agents_sessions_setStatus.await_args.kwargs["status"] == "active"


async def test_approval_suspends_native_session_and_marks_tool_pending() -> None:
    from paid_media_agent.surfaces.slack.blocks import approval_message

    stream = SimpleNamespace(append=AsyncMock(), stop=AsyncMock())
    client = SimpleNamespace(
        agents_sessions_setStatus=AsyncMock(),
        chat_stream=lambda **_kwargs: stream,
    )
    delivery = SlackDelivery(client, channel="C1", thread_ts="1", team="T1", user="U1")
    await delivery.event(RunEvent("start"))
    await delivery.event(RunEvent("tool", id="action-1", name="execute_change"))
    reply = SlackReply(
        "C1",
        "1",
        approval_message("Review the action.", "opaque-route"),
        RunOutcome("thread", "Review the action.", True, None, None),
    )
    await delivery.finish(reply)
    stopped = stream.stop.await_args.kwargs
    assert stopped["session_status"] == "suspended"
    assert stopped["chunks"] == [
        {
            "type": "task_update",
            "id": "action-1",
            "title": "execute change",
            "status": "pending",
        }
    ]
    assert {button["text"]["text"] for button in stopped["blocks"][0]["elements"]} == {
        "Approve",
        "Reject",
    }
