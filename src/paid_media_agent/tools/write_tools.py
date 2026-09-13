"""Model-facing write tools over ProposalService and WriteExecutor: propose, inspect, execute."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from langchain.agents.middleware import InterruptOnConfig
from langchain.agents.middleware.types import ToolCallRequest
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.presentation import ProposalView, ReceiptView
from paid_media_agent.tools.discovery import _NoArgs
from paid_media_agent.tools.writes import (
    DISCOVER_WRITE_OPERATIONS_TOOL,
    EXECUTE_CHANGE_TOOL,
    GET_PROPOSAL_TOOL,
    PROPOSE_CHANGE_TOOL,
    ProposalService,
    WriteDenied,
    WriteExecutor,
)


class ProposeChangeArgs(BaseModel):
    account_alias: str = Field(description="Configured account alias from list_accounts.")
    tool_name: str = Field(
        description="Admitted mutation from discover_write_operations, e.g. google_ads__update_campaign_budget."
    )
    target_ref: str = Field(
        description="Provider entity id being changed, e.g. a campaign id from a read."
    )
    changes: dict[str, JsonValue] = Field(
        description="Field -> new value. Only fields the policy admits."
    )
    reason: str = Field(min_length=1, max_length=2000)
    measurement_plan: str = Field(default="", max_length=800)
    reversal_plan: str = Field(default="", max_length=800)


class ProposalIdArgs(BaseModel):
    proposal_id: str = Field(description="UUID of the proposal returned by propose_change.")


class ExecuteChangeArgs(BaseModel):
    proposal_id: str = Field(description="UUID of the proposal returned by propose_change.")
    revision: int = Field(
        ge=1, description="Revision number of the proposal exactly as you presented it."
    )


def _caller_from_runtime(runtime: Any) -> tuple[str, str]:
    """Use MDA's verified identity, or the caller injected by a local transport."""
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {})
    thread_id = str(configurable.get("thread_id") or "local-thread")
    if hasattr(runtime, "identity"):
        identity = runtime.identity
        user = identity.get("user") if isinstance(identity, Mapping) else None
        actor = user.get("id") if isinstance(user, Mapping) else None
        return thread_id, actor if isinstance(actor, str) else "anonymous"
    return thread_id, str(configurable.get("caller_ref") or "local-user")


def _proposal_id_from_call(tool_call: Mapping[str, Any]) -> UUID | None:
    raw = (
        tool_call.get("args", {}).get("proposal_id")
        if isinstance(tool_call.get("args"), Mapping)
        else None
    )
    try:
        return UUID(str(raw))
    except (ValueError, TypeError):
        return None


def build_execute_interrupt(service: ProposalService) -> InterruptOnConfig:
    """Interrupt only for a proposal that exists on this thread; anything else runs and is denied.

    The predicate is evaluated again when the graph resumes, so it must not depend on state that
    the reviewer's decision changes (a rejection is persisted before the resume). Existence on the
    thread is stable; the executor still refuses anything that is not awaiting approval.
    """

    def _when(request: ToolCallRequest) -> bool:
        proposal_id = _proposal_id_from_call(request.tool_call)
        if proposal_id is None:
            return False
        thread_id, _ = _caller_from_runtime(request.runtime)
        return service.belongs_to(proposal_id, thread_id)

    def _description(tool_call: Any, state: Any, runtime: Any) -> str:  # noqa: ARG001
        proposal_id = _proposal_id_from_call(tool_call)
        record = service.get(proposal_id) if proposal_id is not None else None
        if record is None:
            return "Execute a staged change (proposal not found)."
        cs = record.changeset
        before = ", ".join(f"{fv.field}={fv.value}" for fv in cs.before) or "n/a"
        after = ", ".join(f"{fv.field}={fv.value}" for fv in cs.after) or "n/a"
        flags = ", ".join(cs.risk_flags) or "none"
        return (
            f"{cs.platform.value} {cs.account_ref}: {cs.tool_name} on {cs.target_ref}. "
            f"Before: {before}. After: {after}. Risk: {cs.risk.value} [{flags}]. "
            f"Reason: {cs.reason[:300]} (proposal {cs.proposal_id}, revision {cs.revision})"
        )

    return InterruptOnConfig(
        allowed_decisions=["approve", "reject"], description=_description, when=_when
    )


def build_write_tools(service: ProposalService, executor: WriteExecutor) -> list[BaseTool]:
    async def _propose(
        account_alias: str,
        tool_name: str,
        target_ref: str,
        changes: dict[str, JsonValue],
        reason: str,
        runtime: ToolRuntime,
        measurement_plan: str = "",
        reversal_plan: str = "",
    ) -> str:
        thread_id, caller = _caller_from_runtime(runtime)
        try:
            record = await service.propose(
                thread_id=thread_id,
                requester_ref=caller,
                account_alias=account_alias,
                tool_name=tool_name,
                target_ref=target_ref,
                changes=changes,
                reason=reason,
                measurement_plan=measurement_plan,
                reversal_plan=reversal_plan,
            )
        except WriteDenied as exc:
            return json.dumps({"denied": True, "reason": exc.reason, "detail": exc.detail})
        view = ProposalView.from_record(record)
        return json.dumps(
            {
                "proposal": view.model_dump(mode="json"),
                "next_step": "Write the proposal summary and call execute_change with proposal_id and revision in the same message. The runtime pauses for human approval.",
            }
        )

    async def _execute(proposal_id: str, revision: int, runtime: ToolRuntime) -> str:
        """Runs only after the reviewer approved the interrupt.

        The approval given on the platform's card is recorded here as a signed claim for the acting
        user, but only when the proposal belongs to this thread and is still the revision that was
        presented: `revision` is frozen in the tool call when the card is raised, so an edit made in
        between is refused instead of executing unseen. Surfaces that create the claim themselves
        (the API, the Slack adapter, the demo) pass straight through.
        """
        try:
            pid = UUID(proposal_id)
        except ValueError:
            return json.dumps({"denied": True, "reason": "invalid_proposal_id"})
        thread_id, caller = _caller_from_runtime(runtime)
        record = service.get(pid)
        if record is None or not service.belongs_to(pid, thread_id):
            return json.dumps({"denied": True, "reason": "unknown_proposal"})
        current = record.changeset.revision
        try:
            if service.approvals.latest_unused(pid, current) is None:
                # No host-made claim: the card click is the approval, valid only for the revision
                # that was presented when the card was raised.
                if current != revision:
                    return json.dumps(
                        {
                            "denied": True,
                            "reason": "proposal_revised",
                            "detail": f"revision {current} is current; present it again",
                        }
                    )
                service.approve(pid, approver_ref=caller)
            receipt = await executor.execute(pid)
        except WriteDenied as exc:
            return json.dumps({"denied": True, "reason": exc.reason, "detail": exc.detail})
        return json.dumps({"receipt": ReceiptView.from_receipt(receipt).model_dump(mode="json")})

    def _get(proposal_id: str, runtime: ToolRuntime) -> str:
        try:
            record = service.get(UUID(proposal_id))
        except ValueError:
            return json.dumps({"denied": True, "reason": "invalid_proposal_id"})
        thread_id, _ = _caller_from_runtime(runtime)
        if record is None or not service.belongs_to(record.changeset.proposal_id, thread_id):
            return json.dumps({"denied": True, "reason": "unknown_proposal"})
        return json.dumps({"proposal": ProposalView.from_record(record).model_dump(mode="json")})

    def _discover() -> str:
        return json.dumps(
            {
                "operations": service.admitted_operations(),
                "execution_gate": executor.gate.describe(),
                "note": "Only these operations can be proposed. Each needs a human approval before one execution attempt.",
            }
        )

    propose_tool = StructuredTool.from_function(
        coroutine=_propose,
        name=PROPOSE_CHANGE_TOOL,
        description=(
            "Stage a typed change proposal for one admitted mutation. Reads current provider state for the "
            "before value, computes the digest, and persists it. Nothing is executed."
        ),
        args_schema=ProposeChangeArgs,
    )
    execute_tool = StructuredTool.from_function(
        coroutine=_execute,
        name=EXECUTE_CHANGE_TOOL,
        description=(
            "Request execution of a staged proposal. The runtime interrupts for human approval; the host verifies "
            "the signed approval, runs one mutation attempt, and reads back the result."
        ),
        args_schema=ExecuteChangeArgs,
    )
    get_tool = StructuredTool.from_function(
        func=_get,
        name=GET_PROPOSAL_TOOL,
        description="Read the current persisted state of a proposal by id.",
        args_schema=ProposalIdArgs,
    )
    discover_tool = StructuredTool.from_function(
        func=_discover,
        name=DISCOVER_WRITE_OPERATIONS_TOOL,
        description="List the admitted mutation operations, their editable fields, units, risk, and the current execution gate.",
        args_schema=_NoArgs,
    )
    return [discover_tool, propose_tool, execute_tool, get_tool]
