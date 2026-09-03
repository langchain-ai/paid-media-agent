"""Versioned presentation objects shared by Slack, the API, and the UI."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from paid_media_agent.domain.common import Platform, RiskLevel
from paid_media_agent.domain.proposals import (
    ChangeSet,
    FieldValue,
    ProposalRecord,
    ProposalState,
    WriteReceipt,
)

PRESENTATION_VERSION = "presentation/1"


class ProposalView(BaseModel):
    """Everything a reviewer needs. Derived from the persisted ChangeSet, never from a message."""

    model_config = ConfigDict(frozen=True)

    version: str = PRESENTATION_VERSION
    proposal_id: UUID
    routing_id: str
    revision: int
    state: ProposalState
    platform: Platform
    account_ref: str
    tool_name: str
    target_ref: str
    before: tuple[FieldValue, ...]
    after: tuple[FieldValue, ...]
    reason: str
    risk: RiskLevel
    measurement_plan: str
    reversal_plan: str
    payload_digest: str
    catalog_revision: str
    requester_ref: str
    risk_flags: tuple[str, ...] = ()

    @classmethod
    def from_record(cls, record: ProposalRecord) -> ProposalView:
        cs: ChangeSet = record.changeset
        return cls(
            proposal_id=cs.proposal_id,
            routing_id=record.routing_id,
            revision=cs.revision,
            state=record.state,
            platform=cs.platform,
            account_ref=cs.account_ref,
            tool_name=cs.tool_name,
            target_ref=cs.target_ref,
            before=cs.before,
            after=cs.after,
            reason=cs.reason,
            risk=cs.risk,
            measurement_plan=cs.measurement_plan,
            reversal_plan=cs.reversal_plan,
            payload_digest=cs.payload_digest,
            catalog_revision=cs.catalog_revision,
            requester_ref=cs.requester_ref,
            risk_flags=cs.risk_flags,
        )


class ReceiptView(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: str = PRESENTATION_VERSION
    proposal_id: UUID
    revision: int
    status: str
    mutation_attempted: bool
    provider_acknowledged: bool = False
    verified_state: tuple[FieldValue, ...]
    checked_at: datetime
    reason: str
    readback_attempts: int

    @classmethod
    def from_receipt(cls, receipt: WriteReceipt) -> ReceiptView:
        return cls(
            proposal_id=receipt.proposal_id,
            revision=receipt.revision,
            status=receipt.status,
            mutation_attempted=receipt.mutation_attempted,
            provider_acknowledged=receipt.provider_acknowledged,
            verified_state=receipt.verified_state,
            checked_at=receipt.checked_at,
            reason=receipt.reason,
            readback_attempts=receipt.readback_attempts,
        )


class ReportSummary(BaseModel):
    """Compact report presentation used by Slack, the UI, and the model's final answer."""

    model_config = ConfigDict(frozen=True)

    version: str = PRESENTATION_VERSION
    report_id: str
    title: str
    scope: str
    executive_summary: str
    scorecard: tuple[tuple[str, str], ...]
    """(label, formatted value) pairs rendered by code."""
    platform_lines: tuple[str, ...]
    data_quality: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    reconciled: bool
    generated_at: datetime
