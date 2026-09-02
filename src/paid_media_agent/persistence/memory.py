"""In-memory repositories for tests and the local demo. Not a production persistence profile."""

from __future__ import annotations

from uuid import UUID

from paid_media_agent.domain.proposals import ApprovalClaim, ProposalRecord, WriteReceipt


class InMemoryProposalRepository:
    def __init__(self) -> None:
        self._records: dict[UUID, ProposalRecord] = {}

    def save(self, record: ProposalRecord) -> None:
        self._records[record.changeset.proposal_id] = record

    def get(self, proposal_id: UUID) -> ProposalRecord | None:
        return self._records.get(proposal_id)

    def get_by_routing_id(self, routing_id: str) -> ProposalRecord | None:
        for record in self._records.values():
            if record.routing_id == routing_id:
                return record
        return None

    def list_for_thread(self, thread_id: str) -> list[ProposalRecord]:
        return [r for r in self._records.values() if r.changeset.thread_id == thread_id]


class InMemoryApprovalRepository:
    def __init__(self) -> None:
        self._claims: dict[UUID, ApprovalClaim] = {}
        self._used: set[UUID] = set()

    def save(self, claim: ApprovalClaim) -> None:
        self._claims[claim.claim_id] = claim

    def get(self, claim_id: UUID) -> ApprovalClaim | None:
        return self._claims.get(claim_id)

    def latest_unused(self, proposal_id: UUID, revision: int) -> ApprovalClaim | None:
        candidates = [
            c
            for c in self._claims.values()
            if c.proposal_id == proposal_id
            and c.revision == revision
            and c.claim_id not in self._used
        ]
        candidates.sort(key=lambda c: c.approved_at)
        return candidates[-1] if candidates else None

    def mark_used(self, claim_id: UUID) -> bool:
        if claim_id in self._used or claim_id not in self._claims:
            return False
        self._used.add(claim_id)
        return True


class InMemoryReceiptRepository:
    def __init__(self) -> None:
        self._receipts: dict[UUID, WriteReceipt] = {}

    def save(self, receipt: WriteReceipt) -> None:
        self._receipts[receipt.proposal_id] = receipt

    def get(self, proposal_id: UUID) -> WriteReceipt | None:
        return self._receipts.get(proposal_id)


class InMemoryDedupeStore:
    def __init__(self) -> None:
        self._keys: set[str] = set()

    def seen(self, key: str) -> bool:
        if key in self._keys:
            return True
        self._keys.add(key)
        return False


class InMemoryThreadOwnershipStore:
    def __init__(self) -> None:
        self._owners: dict[str, str] = {}

    def owner(self, thread_id: str) -> str | None:
        return self._owners.get(thread_id)

    def claim(self, thread_id: str, caller_ref: str) -> bool:
        current = self._owners.setdefault(thread_id, caller_ref)
        return current == caller_ref
