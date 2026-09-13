"""Repository protocols. Runtime profiles choose the implementation; policy code does not."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from paid_media_agent.domain.proposals import ApprovalClaim, ProposalRecord, WriteReceipt


class ProposalRepository(Protocol):
    def save(self, record: ProposalRecord, *, expected: ProposalRecord | None = None) -> bool:
        """Insert when absent, or replace only the exact expected record. False means conflict."""
        ...

    def get(self, proposal_id: UUID) -> ProposalRecord | None: ...

    def get_by_routing_id(self, routing_id: str) -> ProposalRecord | None: ...

    def list_for_thread(self, thread_id: str) -> list[ProposalRecord]: ...


class ApprovalRepository(Protocol):
    def save(self, claim: ApprovalClaim) -> None: ...

    def latest_unused(self, proposal_id: UUID, revision: int) -> ApprovalClaim | None: ...

    def mark_used(self, claim_id: UUID) -> bool:
        """Return True the first time a claim is consumed; False on any replay."""
        ...


class ReceiptRepository(Protocol):
    def save(self, receipt: WriteReceipt) -> None: ...

    def get(self, proposal_id: UUID) -> WriteReceipt | None: ...


class DedupeStore(Protocol):
    def seen(self, key: str) -> bool:
        """Record `key` and return True if it was already present."""
        ...


class ThreadOwnershipStore(Protocol):
    def owner(self, thread_id: str) -> str | None: ...

    def claim(self, thread_id: str, caller_ref: str) -> bool:
        """Bind a thread to its first caller. Return False if owned by someone else."""
        ...
