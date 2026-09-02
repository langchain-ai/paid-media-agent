"""Governed-write domain objects, canonical digests, and the proposal state machine."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import JsonValue, OpaqueAccountRef, Platform, RiskLevel

ReceiptStatus = Literal["verified", "rejected", "failed", "unknown"]


class ProposalState(StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    AWAITING_APPROVAL = "awaiting_approval"
    REVISED = "revised"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    REJECTED = "rejected"
    FAILED = "failed"
    UNKNOWN = "unknown"


class ProposalEvent(StrEnum):
    PROPOSE = "propose"
    REQUEST_APPROVAL = "request_approval"
    APPROVE = "approve"
    EDIT = "edit"
    REJECT = "reject"
    START_VERIFY = "start_verify"
    VERIFIED = "verified"
    FAIL = "fail"
    UNKNOWN = "unknown"


_TRANSITIONS: dict[tuple[ProposalState, ProposalEvent], ProposalState] = {
    (ProposalState.DRAFT, ProposalEvent.PROPOSE): ProposalState.PROPOSED,
    (ProposalState.PROPOSED, ProposalEvent.REQUEST_APPROVAL): ProposalState.AWAITING_APPROVAL,
    (ProposalState.AWAITING_APPROVAL, ProposalEvent.APPROVE): ProposalState.EXECUTING,
    (ProposalState.AWAITING_APPROVAL, ProposalEvent.EDIT): ProposalState.REVISED,
    (ProposalState.REVISED, ProposalEvent.REQUEST_APPROVAL): ProposalState.AWAITING_APPROVAL,
    (ProposalState.AWAITING_APPROVAL, ProposalEvent.REJECT): ProposalState.REJECTED,
    (ProposalState.PROPOSED, ProposalEvent.REJECT): ProposalState.REJECTED,
    (ProposalState.REVISED, ProposalEvent.REJECT): ProposalState.REJECTED,
    (ProposalState.EXECUTING, ProposalEvent.START_VERIFY): ProposalState.VERIFYING,
    (ProposalState.VERIFYING, ProposalEvent.VERIFIED): ProposalState.VERIFIED,
    (ProposalState.EXECUTING, ProposalEvent.FAIL): ProposalState.FAILED,
    (ProposalState.VERIFYING, ProposalEvent.FAIL): ProposalState.FAILED,
    (ProposalState.EXECUTING, ProposalEvent.UNKNOWN): ProposalState.UNKNOWN,
    (ProposalState.VERIFYING, ProposalEvent.UNKNOWN): ProposalState.UNKNOWN,
}

TERMINAL_STATES = frozenset(
    {ProposalState.VERIFIED, ProposalState.REJECTED, ProposalState.FAILED, ProposalState.UNKNOWN}
)


class InvalidTransition(Exception):
    def __init__(self, state: ProposalState, event: ProposalEvent) -> None:
        super().__init__(f"cannot apply {event.value} in state {state.value}")
        self.state = state
        self.event = event


def transition(state: ProposalState, event: ProposalEvent) -> ProposalState:
    """Return the next state or raise `InvalidTransition`."""
    try:
        return _TRANSITIONS[(state, event)]
    except KeyError as exc:
        raise InvalidTransition(state, event) from exc


class FieldValue(BaseModel):
    model_config = ConfigDict(frozen=True)

    field: str
    value: JsonValue
    unit: str | None = None


class ChangeSet(BaseModel):
    """Canonical proposal. The review card and the execution payload derive from this object."""

    model_config = ConfigDict(frozen=True)

    proposal_id: UUID
    revision: int = Field(ge=1)
    platform: Platform
    account_ref: OpaqueAccountRef
    tool_name: str
    target_ref: str
    canonical_args: dict[str, JsonValue]
    before: tuple[FieldValue, ...]
    after: tuple[FieldValue, ...]
    reason: str = Field(min_length=1, max_length=2000)
    risk: RiskLevel
    catalog_revision: str
    payload_digest: str
    requester_ref: str
    thread_id: str
    measurement_plan: str = ""
    reversal_plan: str = ""

    def digest_material(self) -> dict[str, JsonValue]:
        """Fields that the digest binds. Presentation-only fields are excluded on purpose."""
        return {
            "proposal_id": str(self.proposal_id),
            "revision": self.revision,
            "platform": self.platform.value,
            "account_ref": self.account_ref,
            "tool_name": self.tool_name,
            "target_ref": self.target_ref,
            "canonical_args": self.canonical_args,
            "before": [fv.model_dump(mode="json") for fv in self.before],
            "after": [fv.model_dump(mode="json") for fv in self.after],
            "catalog_revision": self.catalog_revision,
            "requester_ref": self.requester_ref,
            "thread_id": self.thread_id,
        }


def canonical_json(value: JsonValue) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def compute_payload_digest(material: dict[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def stamp_digest(changeset: ChangeSet) -> ChangeSet:
    """Return a copy whose `payload_digest` matches its digest material."""
    digest = compute_payload_digest(changeset.digest_material())
    return changeset.model_copy(update={"payload_digest": digest})


class ApprovalClaim(BaseModel):
    """Host-created, signed, single-use approval bound to one proposal revision and digest."""

    model_config = ConfigDict(frozen=True)

    claim_id: UUID
    proposal_id: UUID
    revision: int
    payload_digest: str
    account_ref: OpaqueAccountRef
    tool_name: str
    requester_ref: str
    approver_ref: str
    approved_at: datetime
    expires_at: datetime
    nonce: str
    signature: str

    def signing_material(self) -> str:
        return "|".join(
            [
                str(self.claim_id),
                str(self.proposal_id),
                str(self.revision),
                self.payload_digest,
                self.account_ref,
                self.tool_name,
                self.requester_ref,
                self.approver_ref,
                self.approved_at.isoformat(),
                self.expires_at.isoformat(),
                self.nonce,
            ]
        )


class WriteReceipt(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: UUID
    revision: int
    status: ReceiptStatus
    mutation_attempted: bool
    provider_operation_ref: str | None
    verified_state: tuple[FieldValue, ...]
    checked_at: datetime
    catalog_revision: str
    reason: str = ""
    readback_attempts: int = 0


class ProposalRecord(BaseModel):
    """Persisted proposal: current change set, state, and an append-only history."""

    model_config = ConfigDict(frozen=True)

    changeset: ChangeSet
    state: ProposalState
    history: tuple[str, ...] = ()
    routing_id: str
    """Opaque id used by surfaces. It carries no payload."""
