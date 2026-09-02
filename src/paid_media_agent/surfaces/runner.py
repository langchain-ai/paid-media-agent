"""One application service shared by Slack, the API, and the UI. No surface-only powers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.presentation import ProposalView, ReceiptView
from paid_media_agent.domain.proposals import ProposalState
from paid_media_agent.persistence.interfaces import ReceiptRepository, ThreadOwnershipStore
from paid_media_agent.tools.writes import ProposalService, WriteDenied


@dataclass(frozen=True)
class RunOutcome:
    thread_id: str
    text: str
    interrupted: bool
    proposal: ProposalView | None
    receipt: ReceiptView | None


class ThreadAccessDenied(Exception):
    pass


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

    def _latest_proposal(self, thread_id: str) -> ProposalView | None:
        records = self._service.proposals.list_for_thread(thread_id)
        return ProposalView.from_record(records[-1]) if records else None

    def _outcome(self, thread_id: str, state: dict[str, Any], config: RunnableConfig) -> RunOutcome:
        snapshot = self._graph.get_state(config)
        interrupted = bool(snapshot.interrupts)
        messages = state.get("messages", [])
        text = ""
        if messages:
            content = messages[-1].content
            text = content if isinstance(content, str) else str(content)
        proposal = self._latest_proposal(thread_id)
        receipt = None
        if proposal is not None:
            stored = self._receipts.get(proposal.proposal_id)
            receipt = ReceiptView.from_receipt(stored) if stored else None
        if interrupted and proposal is not None:
            text = "A change is waiting for review."
        return RunOutcome(
            thread_id=thread_id,
            text=text,
            interrupted=interrupted,
            proposal=proposal,
            receipt=receipt,
        )

    async def send(self, *, thread_id: str, caller_ref: str, text: str) -> RunOutcome:
        config = self._config(thread_id, caller_ref)
        state = await self._graph.ainvoke(
            {"messages": [{"role": "user", "content": text}]}, config=config
        )
        return self._outcome(thread_id, state, config)

    async def resume(
        self, *, thread_id: str, caller_ref: str, decision: str, message: str = ""
    ) -> RunOutcome:
        config = self._config(thread_id, caller_ref)
        snapshot = self._graph.get_state(config)
        if not snapshot.interrupts:
            return self._outcome(thread_id, snapshot.values, config)
        payload: dict[str, JsonValue] = {"type": decision}
        if decision == "reject" and message:
            payload["message"] = message
        state = await self._graph.ainvoke(Command(resume={"decisions": [payload]}), config=config)
        return self._outcome(thread_id, state, config)

    def proposal_by_routing_id(self, routing_id: str) -> ProposalView | None:
        record = self._service.proposals.get_by_routing_id(routing_id)
        return ProposalView.from_record(record) if record else None

    def proposal(self, proposal_id: UUID) -> ProposalView | None:
        record = self._service.get(proposal_id)
        return ProposalView.from_record(record) if record else None

    async def approve(self, *, proposal_id: UUID, approver_ref: str) -> RunOutcome:
        """Host creates the claim, then the graph resumes and the executor verifies it."""
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        self._service.approve(proposal_id, approver_ref=approver_ref)
        return await self.resume(
            thread_id=record.changeset.thread_id,
            caller_ref=record.changeset.requester_ref,
            decision="approve",
        )

    async def reject(self, *, proposal_id: UUID, actor_ref: str, message: str = "") -> RunOutcome:
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        self._service.reject(proposal_id, actor_ref=actor_ref, message=message)
        return await self.resume(
            thread_id=record.changeset.thread_id,
            caller_ref=record.changeset.requester_ref,
            decision="reject",
            message=message or "rejected by reviewer",
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
