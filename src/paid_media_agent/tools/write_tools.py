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


def _caller_from_config(config: Any) -> tuple[str, str]:
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = str(configurable.get("thread_id") or "local-thread")
    caller = str(configurable.get("caller_ref") or "local-user")
    return thread_id, caller


def _caller_from_runtime(runtime: Any) -> tuple[str, str]:
    return _caller_from_config(getattr(runtime, "config", None) or {})


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
        thread_id, _ = _caller_from_config(getattr(request.runtime, "config", None) or {})
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
            f"Approve change {cs.proposal_id} (revision {cs.revision}, {record.state.value}) on {cs.platform.value} account "
            f"{cs.account_ref}: {cs.tool_name} target {cs.target_ref}. Before: {before}. After: {after}. "
            f"Risk: {cs.risk.value} [{flags}]. Reason: {cs.reason[:300]}"
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
                "next_step": "Present the proposal, then call execute_change with the proposal_id. The runtime pauses for human approval.",
            }
        )

    async def _execute(proposal_id: str) -> str:
        try:
            pid = UUID(proposal_id)
        except ValueError:
            return json.dumps({"denied": True, "reason": "invalid_proposal_id"})
        try:
            receipt = await executor.execute(pid)
        except WriteDenied as exc:
            return json.dumps({"denied": True, "reason": exc.reason, "detail": exc.detail})
        return json.dumps({"receipt": ReceiptView.from_receipt(receipt).model_dump(mode="json")})

    def _get(proposal_id: str) -> str:
        try:
            record = service.get(UUID(proposal_id))
        except ValueError:
            return json.dumps({"denied": True, "reason": "invalid_proposal_id"})
        if record is None:
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
        args_schema=ProposalIdArgs,
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
