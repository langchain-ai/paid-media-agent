"""Run caller-owned conversations and resolve host-approved actions."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.presentation import ProposalView, ReceiptView
from paid_media_agent.domain.proposals import ProposalState
from paid_media_agent.persistence.interfaces import ReceiptRepository, ThreadOwnershipStore
from paid_media_agent.tools.artifacts import ArtifactError, ArtifactStore
from paid_media_agent.tools.reports import RENDER_REPORT_TOOL
from paid_media_agent.tools.writes import ProposalService, WriteDenied


@dataclass(frozen=True)
class RunOutcome:
    thread_id: str
    text: str
    interrupted: bool
    proposal: ProposalView | None
    receipt: ReceiptView | None


@dataclass(frozen=True)
class RunEvent:
    kind: Literal["start", "text", "tool"]
    text: str = ""
    id: str = ""
    name: str = ""
    status: Literal["in_progress", "complete", "error"] = "in_progress"


EventHandler = Callable[[RunEvent], Awaitable[None]]


class ThreadAccessDenied(Exception):
    pass


def _content_text(content: Any) -> str:
    """Model content is a string or a list of blocks; keep only the text either way."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return "\n".join(t for t in texts if t).strip()
    return str(content)


def _last_assistant_text(messages: list[Any]) -> str:
    """Prose from the most recent assistant message, so an interrupt does not discard it."""
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai":
            return _content_text(message.content)[:2000]
    return ""


class AgentRunner:
    """Runs the graph for a caller-owned thread and exposes proposal actions."""

    def __init__(
        self,
        *,
        graph: CompiledStateGraph[Any, Any, Any, Any],
        service: ProposalService,
        receipts: ReceiptRepository,
        threads: ThreadOwnershipStore,
    ) -> None:
        self._graph = graph
        self._service = service
        self._receipts = receipts
        self._threads = threads

    def _config(self, thread_id: str, caller_ref: str) -> RunnableConfig:
        if not self._threads.claim(thread_id, caller_ref):
            raise ThreadAccessDenied("thread belongs to another caller")
        return RunnableConfig(configurable={"thread_id": thread_id, "caller_ref": caller_ref})

    def latest_proposal(self, thread_id: str) -> ProposalView | None:
        records = self._service.proposals.list_for_thread(thread_id)
        return ProposalView.from_record(records[-1]) if records else None

    async def report_files(
        self, *, thread_id: str, caller_ref: str, artifacts: ArtifactStore
    ) -> set[str]:
        if self._threads.owner(thread_id) != caller_ref:
            raise ThreadAccessDenied("thread belongs to another caller")
        config = RunnableConfig(configurable={"thread_id": thread_id, "caller_ref": caller_ref})
        snapshot = await self._graph.aget_state(config)
        files: set[str] = set()
        for message in snapshot.values.get("messages", []):
            if not isinstance(message, ToolMessage) or message.name != RENDER_REPORT_TOOL:
                continue
            if message.status == "error" or not isinstance(message.content, str):
                continue
            try:
                result = json.loads(message.content)
                if isinstance(result, dict) and result.get("offloaded"):
                    record = artifacts.read(result["artifact_id"])
                    if record.metadata.tool_name != RENDER_REPORT_TOOL or not isinstance(
                        record.payload, dict
                    ):
                        continue
                    result = json.loads(str(record.payload.get("content", "")))
            except (ValueError, KeyError, TypeError, ArtifactError):
                continue
            if isinstance(result, dict):
                for file in result.get("files", []):
                    if isinstance(file, dict) and isinstance(file.get("path"), str):
                        files.add(file["path"])
        return files

    async def _outcome(
        self, thread_id: str, state: dict[str, Any], config: RunnableConfig
    ) -> RunOutcome:
        snapshot = await self._graph.aget_state(config)
        interrupted = bool(snapshot.interrupts)
        messages = state.get("messages", [])
        text = ""
        if messages:
            text = _content_text(messages[-1].content)
        proposal = self.latest_proposal(thread_id)
        receipt = None
        if proposal is not None:
            stored = self._receipts.get(proposal.proposal_id)
            receipt = ReceiptView.from_receipt(stored) if stored else None
        if interrupted and proposal is not None:
            prose = _last_assistant_text(messages)
            text = (prose + "\n\n" if prose else "") + "A change is waiting for review."
        return RunOutcome(
            thread_id=thread_id,
            text=text,
            interrupted=interrupted,
            proposal=proposal,
            receipt=receipt,
        )

    async def _run(
        self, inputs: Any, config: RunnableConfig, on_event: EventHandler | None
    ) -> dict[str, Any]:
        if on_event is None:
            return await self._graph.ainvoke(inputs, config=config)
        await on_event(RunEvent("start"))
        started: set[str] = set()
        completed: set[str] = set()
        async for chunk in self._graph.astream(
            inputs, config=config, stream_mode=["messages", "updates"]
        ):
            if not isinstance(chunk, tuple) or len(chunk) != 2:
                continue
            mode, data = chunk
            if mode == "messages":
                message, metadata = data
                if isinstance(message, AIMessage) and metadata.get("langgraph_node") == "model":
                    content = message.content
                    text = (
                        content
                        if isinstance(content, str)
                        else "".join(
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        )
                    )
                    if text:
                        await on_event(RunEvent("text", text=text, id=message.id or ""))
            elif mode == "updates" and isinstance(data, dict):
                for update in data.values():
                    if not isinstance(update, dict):
                        continue
                    messages = update.get("messages", [])
                    if not isinstance(messages, list):
                        messages = [messages]
                    for message in messages:
                        if isinstance(message, AIMessage):
                            for call in message.tool_calls:
                                call_id = call.get("id") or ""
                                if call_id and call_id not in started:
                                    started.add(call_id)
                                    await on_event(RunEvent("tool", id=call_id, name=call["name"]))
                        elif (
                            isinstance(message, ToolMessage)
                            and message.tool_call_id not in completed
                        ):
                            completed.add(message.tool_call_id)
                            await on_event(
                                RunEvent(
                                    "tool",
                                    id=message.tool_call_id,
                                    name=message.name or "Tool",
                                    status="error" if message.status == "error" else "complete",
                                )
                            )
        return (await self._graph.aget_state(config)).values

    async def send(
        self, *, thread_id: str, caller_ref: str, text: str, on_event: EventHandler | None = None
    ) -> RunOutcome:
        config = self._config(thread_id, caller_ref)
        state = await self._run({"messages": [{"role": "user", "content": text}]}, config, on_event)
        return await self._outcome(thread_id, state, config)

    async def resume(
        self,
        *,
        thread_id: str,
        caller_ref: str,
        decision: str,
        message: str = "",
        on_event: EventHandler | None = None,
    ) -> RunOutcome:
        config = self._config(thread_id, caller_ref)
        snapshot = await self._graph.aget_state(config)
        if not snapshot.interrupts:
            return await self._outcome(thread_id, snapshot.values, config)
        payload: dict[str, JsonValue] = {"type": decision}
        if decision == "reject" and message:
            payload["message"] = message
        state = await self._run(Command(resume={"decisions": [payload]}), config, on_event)
        return await self._outcome(thread_id, state, config)

    def proposal_by_routing_id(self, routing_id: str) -> ProposalView | None:
        record = self._service.proposals.get_by_routing_id(routing_id)
        return ProposalView.from_record(record) if record else None

    def proposal(self, proposal_id: UUID) -> ProposalView | None:
        record = self._service.get(proposal_id)
        return ProposalView.from_record(record) if record else None

    async def approve(
        self, *, proposal_id: UUID, approver_ref: str, on_event: EventHandler | None = None
    ) -> RunOutcome:
        """Host creates the claim, then the graph resumes and the executor verifies it."""
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        self._service.approve(proposal_id, approver_ref=approver_ref)
        return await self.resume(
            thread_id=record.changeset.thread_id,
            caller_ref=record.changeset.requester_ref,
            decision="approve",
            on_event=on_event,
        )

    async def reject(
        self,
        *,
        proposal_id: UUID,
        actor_ref: str,
        message: str = "",
        on_event: EventHandler | None = None,
    ) -> RunOutcome:
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        self._service.reject(proposal_id, actor_ref=actor_ref, message=message)
        return await self.resume(
            thread_id=record.changeset.thread_id,
            caller_ref=record.changeset.requester_ref,
            decision="reject",
            message=message or "rejected by reviewer",
            on_event=on_event,
        )

    def edit(
        self, *, proposal_id: UUID, editor_ref: str, changes: dict[str, JsonValue]
    ) -> ProposalView:
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        if record.state is not ProposalState.AWAITING_APPROVAL:
            raise WriteDenied("not_awaiting_approval", record.state.value)
        updated = self._service.revise(proposal_id, editor_ref=editor_ref, changes=changes)
        return ProposalView.from_record(updated)

    def receipt(self, proposal_id: UUID) -> ReceiptView | None:
        stored = self._receipts.get(proposal_id)
        return ReceiptView.from_receipt(stored) if stored else None
