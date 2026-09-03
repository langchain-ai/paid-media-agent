"""Postgres repositories for the self-hosted profile. Parameterized SQL only."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from paid_media_agent.domain.proposals import ApprovalClaim, ProposalRecord, WriteReceipt

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pma_proposals (
    proposal_id UUID PRIMARY KEY,
    routing_id TEXT NOT NULL UNIQUE,
    thread_id TEXT NOT NULL,
    state TEXT NOT NULL,
    record JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pma_proposals_thread_idx ON pma_proposals (thread_id);
CREATE TABLE IF NOT EXISTS pma_approvals (
    claim_id UUID PRIMARY KEY,
    proposal_id UUID NOT NULL,
    revision INTEGER NOT NULL,
    approved_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ NULL,
    claim JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS pma_approvals_proposal_idx ON pma_approvals (proposal_id, revision);
CREATE TABLE IF NOT EXISTS pma_receipts (
    proposal_id UUID PRIMARY KEY,
    receipt JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pma_dedupe (
    dedupe_key TEXT PRIMARY KEY,
    seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS pma_thread_owners (
    thread_id TEXT PRIMARY KEY,
    caller_ref TEXT NOT NULL
);
"""


class PostgresRepositories:
    """One connection pool, several repositories. Call `setup()` once per deployment."""

    def __init__(self, conn_string: str) -> None:
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(conn_string, min_size=1, max_size=4, open=True)
        self.proposals = PostgresProposalRepository(self._pool)
        self.approvals = PostgresApprovalRepository(self._pool)
        self.receipts = PostgresReceiptRepository(self._pool)
        self.dedupe = PostgresDedupeStore(self._pool)
        self.threads = PostgresThreadOwnershipStore(self._pool)

    def setup(self) -> None:
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)
            conn.commit()

    def close(self) -> None:
        self._pool.close()


class PostgresProposalRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def save(self, record: ProposalRecord) -> None:
        payload = json.dumps(record.model_dump(mode="json"))
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pma_proposals (proposal_id, routing_id, thread_id, state, record)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (proposal_id) DO UPDATE
                SET routing_id = EXCLUDED.routing_id, state = EXCLUDED.state, record = EXCLUDED.record, updated_at = now()
                """,
                (
                    record.changeset.proposal_id,
                    record.routing_id,
                    record.changeset.thread_id,
                    record.state.value,
                    payload,
                ),
            )
            conn.commit()

    def _load(self, row: Any) -> ProposalRecord | None:
        if row is None:
            return None
        data = row[0] if not isinstance(row[0], str) else json.loads(row[0])
        return ProposalRecord.model_validate(data)

    def get(self, proposal_id: UUID) -> ProposalRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT record FROM pma_proposals WHERE proposal_id = %s", (proposal_id,)
            ).fetchone()
        return self._load(row)

    def get_by_routing_id(self, routing_id: str) -> ProposalRecord | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT record FROM pma_proposals WHERE routing_id = %s", (routing_id,)
            ).fetchone()
        return self._load(row)

    def list_for_thread(self, thread_id: str) -> list[ProposalRecord]:
        with self._pool.connection() as conn:
            rows = conn.execute(
                "SELECT record FROM pma_proposals WHERE thread_id = %s ORDER BY updated_at",
                (thread_id,),
            ).fetchall()
        return [r for r in (self._load(row) for row in rows) if r is not None]


class PostgresApprovalRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def save(self, claim: ApprovalClaim) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pma_approvals (claim_id, proposal_id, revision, approved_at, claim)
                VALUES (%s, %s, %s, %s, %s::jsonb) ON CONFLICT (claim_id) DO NOTHING
                """,
                (
                    claim.claim_id,
                    claim.proposal_id,
                    claim.revision,
                    claim.approved_at,
                    json.dumps(claim.model_dump(mode="json")),
                ),
            )
            conn.commit()

    def latest_unused(self, proposal_id: UUID, revision: int) -> ApprovalClaim | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                """
                SELECT claim FROM pma_approvals
                WHERE proposal_id = %s AND revision = %s AND used_at IS NULL
                ORDER BY approved_at DESC LIMIT 1
                """,
                (proposal_id, revision),
            ).fetchone()
        if row is None:
            return None
        data = row[0] if not isinstance(row[0], str) else json.loads(row[0])
        return ApprovalClaim.model_validate(data)

    def mark_used(self, claim_id: UUID) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                "UPDATE pma_approvals SET used_at = now() WHERE claim_id = %s AND used_at IS NULL",
                (claim_id,),
            )
            conn.commit()
            return bool(cursor.rowcount == 1)


class PostgresReceiptRepository:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def save(self, receipt: WriteReceipt) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO pma_receipts (proposal_id, receipt) VALUES (%s, %s::jsonb)
                ON CONFLICT (proposal_id) DO UPDATE SET receipt = EXCLUDED.receipt, created_at = now()
                """,
                (receipt.proposal_id, json.dumps(receipt.model_dump(mode="json"))),
            )
            conn.commit()

    def get(self, proposal_id: UUID) -> WriteReceipt | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT receipt FROM pma_receipts WHERE proposal_id = %s", (proposal_id,)
            ).fetchone()
        if row is None:
            return None
        data = row[0] if not isinstance(row[0], str) else json.loads(row[0])
        return WriteReceipt.model_validate(data)


class PostgresDedupeStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def seen(self, key: str) -> bool:
        with self._pool.connection() as conn:
            cursor = conn.execute(
                "INSERT INTO pma_dedupe (dedupe_key) VALUES (%s) ON CONFLICT DO NOTHING", (key,)
            )
            conn.commit()
            return bool(cursor.rowcount == 0)


class PostgresThreadOwnershipStore:
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    def owner(self, thread_id: str) -> str | None:
        with self._pool.connection() as conn:
            row = conn.execute(
                "SELECT caller_ref FROM pma_thread_owners WHERE thread_id = %s", (thread_id,)
            ).fetchone()
        return None if row is None else str(row[0])

    def claim(self, thread_id: str, caller_ref: str) -> bool:
        with self._pool.connection() as conn:
            conn.execute(
                "INSERT INTO pma_thread_owners (thread_id, caller_ref) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (thread_id, caller_ref),
            )
            conn.commit()
        return self.owner(thread_id) == caller_ref
