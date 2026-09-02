"""Governed writes: typed proposals, host-created signed approvals, one attempt, bounded readback."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging
import secrets
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any
from uuid import UUID

import jsonschema
from langchain.tools import ToolRuntime
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.common import JsonValue, Platform, RiskLevel
from paid_media_agent.domain.presentation import ProposalView, ReceiptView
from paid_media_agent.domain.proposals import (
    ApprovalClaim,
    ChangeSet,
    FieldValue,
    InvalidTransition,
    ProposalEvent,
    ProposalRecord,
    ProposalState,
    ReceiptStatus,
    WriteReceipt,
    compute_payload_digest,
    stamp_digest,
    transition,
)
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.persistence.interfaces import (
    ApprovalRepository,
    ProposalRepository,
    ReceiptRepository,
)
from paid_media_agent.tools.catalog import CatalogEntry, CatalogProvider, ToolClass
from paid_media_agent.tools.providers import (
    ProviderError,
    ProviderTimeout,
    ReadProvider,
    WriteProvider,
)

logger = logging.getLogger(__name__)

PROPOSE_CHANGE_TOOL = "propose_change"
EXECUTE_CHANGE_TOOL = "execute_change"
GET_PROPOSAL_TOOL = "get_proposal"

DEFAULT_READBACK_ATTEMPTS = 3
DEFAULT_READBACK_SECONDS = 20.0
DEFAULT_MUTATION_TIMEOUT_SECONDS = 30.0


class WriteOperation(BaseModel):
    """One admitted mutation: which read proves its state and which fields it may change."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    readback_tool: str
    target_arg: str
    editable_fields: tuple[str, ...]
    readback_fields: dict[str, str]
    """Maps proposal field -> field name in the readback payload."""
    risk: RiskLevel
    units: dict[str, str] = Field(default_factory=dict)
    readback_entity_key: str | None = "campaign"
    """Key holding the entity object inside the readback payload, or None for a flat payload."""


class WritePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    operations: tuple[WriteOperation, ...]

    def get(self, tool_name: str) -> WriteOperation | None:
        for op in self.operations:
            if op.tool_name == tool_name:
                return op
        return None


def fixture_write_policy() -> WritePolicy:
    ops: list[WriteOperation] = []
    for platform in Platform:
        prefix = f"{platform.value}__"
        ops.append(
            WriteOperation(
                tool_name=f"{prefix}update_campaign_budget",
                readback_tool=f"{prefix}get_campaign",
                target_arg="campaign_id",
                editable_fields=("daily_budget",),
                readback_fields={"daily_budget": "daily_budget"},
                risk=RiskLevel.MEDIUM,
                units={"daily_budget": "account currency per day"},
            )
        )
        ops.append(
            WriteOperation(
                tool_name=f"{prefix}update_campaign_status",
                readback_tool=f"{prefix}get_campaign",
                target_arg="campaign_id",
                editable_fields=("status",),
                readback_fields={"status": "status"},
                risk=RiskLevel.HIGH,
            )
        )
    return WritePolicy(operations=tuple(ops))


class ApprovalPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    approver_refs: frozenset[str]
    allow_self_approval: bool = False
    ttl_seconds: int = 900

    def may_approve(self, approver_ref: str, requester_ref: str) -> tuple[bool, str]:
        if approver_ref not in self.approver_refs:
            return False, "approver is not an authorized approver"
        if approver_ref == requester_ref and not self.allow_self_approval:
            return False, "self-approval is not allowed"
        return True, "ok"


class ApprovalSigner:
    """HMAC-SHA256 over the claim material. The key never leaves the host."""

    def __init__(self, key: bytes) -> None:
        if len(key) < 16:
            raise ValueError("approval signing key must be at least 16 bytes")
        self._key = key

    @classmethod
    def ephemeral(cls) -> ApprovalSigner:
        return cls(secrets.token_bytes(32))

    def sign(self, material: str) -> str:
        return hmac.new(self._key, material.encode("utf-8"), sha256).hexdigest()

    def verify(self, material: str, signature: str) -> bool:
        return hmac.compare_digest(self.sign(material), signature)


class WriteDenied(Exception):
    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason if not detail else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


class WriteGate:
    """Global kill switch for live providers. Fakes are always allowed; they cannot spend money."""

    def __init__(self, *, writes_enabled: bool, provider_is_fake: bool) -> None:
        self.writes_enabled = writes_enabled
        self.provider_is_fake = provider_is_fake

    def check(self) -> None:
        if self.provider_is_fake:
            return
        if not self.writes_enabled:
            raise WriteDenied("writes_disabled", "PAID_MEDIA_WRITES_ENABLED is false")
        raise WriteDenied(
            "live_writes_not_released", "live provider mutations require the Slice 6 canary release"
        )


Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json_ready(value: JsonValue) -> JsonValue:
    if isinstance(value, Decimal):
        return str(value)
    return value


async def read_entity_state(
    provider: ReadProvider,
    entry: CatalogEntry,
    arguments: dict[str, JsonValue],
    operation: WriteOperation,
) -> dict[str, JsonValue]:
    """Read the target entity through the authorized read provider and extract its fields."""
    result = await provider.call_read(entry, arguments)
    payload = result.payload
    if operation.readback_entity_key is not None:
        entity = payload.get(operation.readback_entity_key)
        if not isinstance(entity, dict):
            raise ProviderError("readback payload did not contain the target entity")
        return dict(entity)
    return dict(payload)


def values_equal(left: JsonValue, right: JsonValue) -> bool:
    """Compare provider values exactly: numerically when both are numbers, else as strings."""
    if isinstance(left, bool) or isinstance(right, bool):
        return left is right
    try:
        return Decimal(str(left)) == Decimal(str(right))
    except (InvalidOperation, ValueError):
        return str(left) == str(right)


class ProposalService:
    """Creates, revises, rejects, and approves proposals. Only this code makes claims."""

    def __init__(
        self,
        *,
        catalog_provider: CatalogProvider,
        accounts: AccountRegistry,
        write_policy: WritePolicy,
        approval_policy: ApprovalPolicy,
        signer: ApprovalSigner,
        proposals: ProposalRepository,
        approvals: ApprovalRepository,
        read_provider: ReadProvider,
        clock: Clock = utc_now,
    ) -> None:
        self._catalog_provider = catalog_provider
        self._accounts = accounts
        self._write_policy = write_policy
        self._approval_policy = approval_policy
        self._signer = signer
        self._proposals = proposals
        self._approvals = approvals
        self._read_provider = read_provider
        self._clock = clock

    @property
    def proposals(self) -> ProposalRepository:
        return self._proposals

    def _resolve_mutation(self, tool_name: str) -> tuple[CatalogEntry, WriteOperation, str]:
        catalog = self._catalog_provider.current()
        entry = catalog.get(tool_name)
        if entry is None:
            raise WriteDenied("unknown_tool", "not in the current authorized catalog")
        if entry.tool_class is not ToolClass.MUTATION:
            raise WriteDenied("not_an_admitted_mutation", entry.policy.reason)
        operation = self._write_policy.get(tool_name)
        if operation is None:
            raise WriteDenied("no_write_policy", "tool is not covered by the reviewed write policy")
        return entry, operation, catalog.revision

    def _scoped_args(
        self,
        entry: CatalogEntry,
        alias: str,
        target_ref: str,
        operation: WriteOperation,
        changes: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        binding = self._accounts.resolve(alias)
        if binding is None:
            raise WriteDenied("unknown_account_alias", alias)
        if binding.platform is not entry.platform:
            raise WriteDenied(
                "platform_scope", f"alias {alias} is not a {entry.platform.value} account"
            )
        if entry.account_arg is None:
            raise WriteDenied("no_account_scope")
        for field in changes:
            if field not in operation.editable_fields:
                raise WriteDenied("field_not_editable", field)
        if not changes:
            raise WriteDenied("no_changes")
        args: dict[str, JsonValue] = {
            entry.account_arg: binding.provider_account_id,
            operation.target_arg: target_ref,
        }
        args.update({k: _json_ready(v) for k, v in changes.items()})
        try:
            jsonschema.validate(instance=args, schema=entry.input_schema)
        except jsonschema.ValidationError as exc:
            raise WriteDenied("schema_validation_failed", sanitize_exception(exc)[:200]) from None
        return args

    async def _current_state(
        self, entry: CatalogEntry, operation: WriteOperation, args: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        readback_entry = self._catalog_provider.current().get(operation.readback_tool)
        if readback_entry is None or readback_entry.tool_class is not ToolClass.READ:
            raise WriteDenied("readback_tool_unavailable", operation.readback_tool)
        read_args: dict[str, JsonValue] = {
            k: v for k, v in args.items() if k in (entry.account_arg, operation.target_arg)
        }
        try:
            return await read_entity_state(
                self._read_provider, readback_entry, read_args, operation
            )
        except ProviderError as exc:
            raise WriteDenied("target_not_readable", sanitize_exception(exc)) from None

    async def propose(
        self,
        *,
        thread_id: str,
        requester_ref: str,
        account_alias: str,
        tool_name: str,
        target_ref: str,
        changes: dict[str, JsonValue],
        reason: str,
        measurement_plan: str = "",
        reversal_plan: str = "",
    ) -> ProposalRecord:
        entry, operation, catalog_revision = self._resolve_mutation(tool_name)
        args = self._scoped_args(entry, account_alias, target_ref, operation, changes)
        state = await self._current_state(entry, operation, args)
        before = tuple(
            FieldValue(
                field=f,
                value=_json_ready(state.get(operation.readback_fields[f])),
                unit=operation.units.get(f),
            )
            for f in changes
        )
        after = tuple(
            FieldValue(field=f, value=_json_ready(v), unit=operation.units.get(f))
            for f, v in changes.items()
        )
        changeset = stamp_digest(
            ChangeSet(
                proposal_id=uuid.uuid4(),
                revision=1,
                platform=entry.platform,
                account_ref=account_alias,
                tool_name=tool_name,
                target_ref=target_ref,
                canonical_args=args,
                before=before,
                after=after,
                reason=reason,
                risk=operation.risk,
                catalog_revision=catalog_revision,
                payload_digest="",
                requester_ref=requester_ref,
                thread_id=thread_id,
                measurement_plan=measurement_plan,
                reversal_plan=reversal_plan,
            )
        )
        state_value = transition(
            transition(ProposalState.DRAFT, ProposalEvent.PROPOSE), ProposalEvent.REQUEST_APPROVAL
        )
        record = ProposalRecord(
            changeset=changeset,
            state=state_value,
            history=(f"{self._clock().isoformat()} proposed by {requester_ref}",),
            routing_id=secrets.token_urlsafe(18),
        )
        self._proposals.save(record)
        return record

    def get(self, proposal_id: UUID) -> ProposalRecord | None:
        return self._proposals.get(proposal_id)

    def revise(
        self, proposal_id: UUID, *, editor_ref: str, changes: dict[str, JsonValue]
    ) -> ProposalRecord:
        record = self._require(proposal_id)
        entry, operation, catalog_revision = self._resolve_mutation(record.changeset.tool_name)
        next_state = transition(record.state, ProposalEvent.EDIT)
        args = self._scoped_args(
            entry, record.changeset.account_ref, record.changeset.target_ref, operation, changes
        )
        after = tuple(
            FieldValue(field=f, value=_json_ready(v), unit=operation.units.get(f))
            for f, v in changes.items()
        )
        before = tuple(fv for fv in record.changeset.before if fv.field in changes)
        if {fv.field for fv in before} != set(changes):
            raise WriteDenied("field_not_editable", "edits must keep the proposed fields")
        changeset = stamp_digest(
            record.changeset.model_copy(
                update={
                    "revision": record.changeset.revision + 1,
                    "canonical_args": args,
                    "before": before,
                    "after": after,
                    "catalog_revision": catalog_revision,
                }
            )
        )
        state_value = transition(next_state, ProposalEvent.REQUEST_APPROVAL)
        updated = ProposalRecord(
            changeset=changeset,
            state=state_value,
            history=(*record.history, f"{self._clock().isoformat()} revised by {editor_ref}"),
            routing_id=secrets.token_urlsafe(18),
        )
        self._proposals.save(updated)
        return updated

    def reject(self, proposal_id: UUID, *, actor_ref: str, message: str = "") -> ProposalRecord:
        record = self._require(proposal_id)
        state_value = transition(record.state, ProposalEvent.REJECT)
        updated = record.model_copy(
            update={
                "state": state_value,
                "history": (
                    *record.history,
                    f"{self._clock().isoformat()} rejected by {actor_ref}: {message[:200]}",
                ),
            }
        )
        self._proposals.save(updated)
        return updated

    def approve(self, proposal_id: UUID, *, approver_ref: str) -> ApprovalClaim:
        """Create a signed, single-use claim bound to the current revision and digest."""
        record = self._require(proposal_id)
        if record.state is not ProposalState.AWAITING_APPROVAL:
            raise WriteDenied("not_awaiting_approval", record.state.value)
        allowed, why = self._approval_policy.may_approve(
            approver_ref, record.changeset.requester_ref
        )
        if not allowed:
            raise WriteDenied("approver_policy", why)
        cs = record.changeset
        if compute_payload_digest(cs.digest_material()) != cs.payload_digest:
            raise WriteDenied("digest_mismatch", "persisted proposal does not match its digest")
        now = self._clock()
        claim = ApprovalClaim(
            claim_id=uuid.uuid4(),
            proposal_id=cs.proposal_id,
            revision=cs.revision,
            payload_digest=cs.payload_digest,
            account_ref=cs.account_ref,
            tool_name=cs.tool_name,
            requester_ref=cs.requester_ref,
            approver_ref=approver_ref,
            approved_at=now,
            expires_at=now + timedelta(seconds=self._approval_policy.ttl_seconds),
            nonce=secrets.token_hex(16),
            signature="",
        )
        claim = claim.model_copy(update={"signature": self._signer.sign(claim.signing_material())})
        self._approvals.save(claim)
        self._proposals.save(
            record.model_copy(
                update={
                    "history": (*record.history, f"{now.isoformat()} approved by {approver_ref}")
                }
            )
        )
        return claim

    def _require(self, proposal_id: UUID) -> ProposalRecord:
        record = self._proposals.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        return record

    def mark(self, proposal_id: UUID, event: ProposalEvent, note: str) -> ProposalRecord:
        record = self._require(proposal_id)
        try:
            state_value = transition(record.state, event)
        except InvalidTransition as exc:
            raise WriteDenied("invalid_transition", str(exc)) from None
        updated = record.model_copy(
            update={"state": state_value, "history": (*record.history, note)}
        )
        self._proposals.save(updated)
        return updated


class WriteExecutor:
    """Verifies the claim, records the attempt, calls the provider once, reads back, reports."""

    def __init__(
        self,
        *,
        service: ProposalService,
        catalog_provider: CatalogProvider,
        write_policy: WritePolicy,
        accounts: AccountRegistry,
        signer: ApprovalSigner,
        approvals: ApprovalRepository,
        receipts: ReceiptRepository,
        provider: WriteProvider,
        read_provider: ReadProvider,
        gate: WriteGate,
        clock: Clock = utc_now,
        sleeper: Callable[[float], Awaitable[None]] | None = None,
        readback_attempts: int = DEFAULT_READBACK_ATTEMPTS,
        readback_seconds: float = DEFAULT_READBACK_SECONDS,
        mutation_timeout_seconds: float = DEFAULT_MUTATION_TIMEOUT_SECONDS,
    ) -> None:
        self._service = service
        self._catalog_provider = catalog_provider
        self._write_policy = write_policy
        self._accounts = accounts
        self._signer = signer
        self._approvals = approvals
        self._receipts = receipts
        self._provider = provider
        self._read_provider = read_provider
        self._gate = gate
        self._clock = clock
        self._sleep = sleeper or asyncio.sleep
        self._readback_attempts = max(1, readback_attempts)
        self._readback_seconds = readback_seconds
        self._mutation_timeout = mutation_timeout_seconds

    def _verify_claim(self, record: ProposalRecord, claim: ApprovalClaim) -> None:
        cs = record.changeset
        if not self._signer.verify(claim.signing_material(), claim.signature):
            raise WriteDenied("invalid_signature")
        if claim.proposal_id != cs.proposal_id or claim.revision != cs.revision:
            raise WriteDenied("stale_approval", "claim is for a different revision")
        if compute_payload_digest(cs.digest_material()) != cs.payload_digest:
            raise WriteDenied("digest_mismatch", "persisted proposal was altered")
        if claim.payload_digest != cs.payload_digest:
            raise WriteDenied("digest_mismatch", "claim digest does not match the proposal")
        if claim.account_ref != cs.account_ref or claim.tool_name != cs.tool_name:
            raise WriteDenied("scope_mismatch", "claim is bound to a different account or tool")
        if claim.requester_ref != cs.requester_ref:
            raise WriteDenied("requester_mismatch")
        now = self._clock()
        if now >= claim.expires_at or claim.approved_at > now + timedelta(seconds=5):
            raise WriteDenied("approval_expired")

    def _verify_catalog(
        self, record: ProposalRecord
    ) -> tuple[CatalogEntry, WriteOperation, CatalogEntry, str]:
        catalog = self._catalog_provider.current()
        cs = record.changeset
        entry = catalog.get(cs.tool_name)
        if entry is None or entry.tool_class is not ToolClass.MUTATION:
            raise WriteDenied("stale_catalog", "mutation tool is no longer authorized")
        operation = self._write_policy.get(cs.tool_name)
        if operation is None:
            raise WriteDenied("no_write_policy")
        readback = catalog.get(operation.readback_tool)
        if readback is None or readback.tool_class is not ToolClass.READ:
            raise WriteDenied("stale_catalog", "readback tool is no longer authorized")
        try:
            jsonschema.validate(instance=cs.canonical_args, schema=entry.input_schema)
        except jsonschema.ValidationError:
            raise WriteDenied(
                "stale_catalog", "current tool schema rejects the approved payload"
            ) from None
        binding = self._accounts.resolve(cs.account_ref)
        if binding is None or binding.provider_account_id != cs.canonical_args.get(
            entry.account_arg or ""
        ):
            raise WriteDenied(
                "account_scope", "proposal account no longer resolves to the same provider account"
            )
        return entry, operation, readback, catalog.revision

    def _receipt(
        self,
        record: ProposalRecord,
        status: ReceiptStatus,
        *,
        attempted: bool,
        op_ref: str | None,
        verified: tuple[FieldValue, ...],
        catalog_revision: str,
        reason: str,
        readback_attempts: int = 0,
    ) -> WriteReceipt:
        receipt = WriteReceipt(
            proposal_id=record.changeset.proposal_id,
            revision=record.changeset.revision,
            status=status,
            mutation_attempted=attempted,
            provider_operation_ref=op_ref,
            verified_state=verified,
            checked_at=self._clock(),
            catalog_revision=catalog_revision,
            reason=reason,
            readback_attempts=readback_attempts,
        )
        self._receipts.save(receipt)
        return receipt

    async def _readback(
        self,
        record: ProposalRecord,
        operation: WriteOperation,
        readback_entry: CatalogEntry,
        entry: CatalogEntry,
    ) -> tuple[str, tuple[FieldValue, ...], int]:
        """Bounded read-only reconciliation. Returns (outcome, observed, attempts)."""
        cs = record.changeset
        read_args = {
            k: v
            for k, v in cs.canonical_args.items()
            if k in (entry.account_arg, operation.target_arg)
        }
        expected = {fv.field: fv.value for fv in cs.after}
        before = {fv.field: fv.value for fv in cs.before}
        deadline = self._clock() + timedelta(seconds=self._readback_seconds)
        attempts = 0
        observed: tuple[FieldValue, ...] = ()
        while attempts < self._readback_attempts and self._clock() <= deadline:
            attempts += 1
            try:
                state = await read_entity_state(
                    self._read_provider, readback_entry, read_args, operation
                )
            except ProviderError:
                await self._sleep(0)
                continue
            observed = tuple(
                FieldValue(
                    field=f,
                    value=_json_ready(state.get(operation.readback_fields[f])),
                    unit=operation.units.get(f),
                )
                for f in expected
            )
            actual = {fv.field: fv.value for fv in observed}
            if all(values_equal(actual.get(f), v) for f, v in expected.items()):
                return "matches_after", observed, attempts
            if all(values_equal(actual.get(f), v) for f, v in before.items()):
                await self._sleep(0)
                continue
        if observed and all(
            values_equal({fv.field: fv.value for fv in observed}.get(f), v)
            for f, v in before.items()
        ):
            return "matches_before", observed, attempts
        return "unproven", observed, attempts

    async def execute(self, proposal_id: UUID) -> WriteReceipt:
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        catalog_revision = self._catalog_provider.current().revision
        if record.state is not ProposalState.AWAITING_APPROVAL:
            return self._receipt(
                record,
                "rejected",
                attempted=False,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason=f"proposal is {record.state.value}",
            )
        claim = self._approvals.latest_unused(
            record.changeset.proposal_id, record.changeset.revision
        )
        if claim is None:
            return self._receipt(
                record,
                "rejected",
                attempted=False,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason="no valid approval claim for this revision",
            )
        try:
            self._verify_claim(record, claim)
            entry, operation, readback_entry, catalog_revision = self._verify_catalog(record)
            self._gate.check()
        except WriteDenied as exc:
            self._service.mark(
                proposal_id,
                ProposalEvent.REJECT,
                f"{self._clock().isoformat()} execution refused: {exc.reason}",
            )
            return self._receipt(
                record,
                "rejected",
                attempted=False,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason=f"{exc.reason}: {exc.detail}".rstrip(": "),
            )
        if not self._approvals.mark_used(claim.claim_id):
            self._service.mark(proposal_id, ProposalEvent.REJECT, "approval replay refused")
            return self._receipt(
                record,
                "rejected",
                attempted=False,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason="approval already used",
            )

        record = self._service.mark(
            proposal_id,
            ProposalEvent.APPROVE,
            f"{self._clock().isoformat()} executing with claim {claim.claim_id}",
        )
        attempted = True
        op_ref: str | None = None
        outcome_reason = ""
        try:
            response = await asyncio.wait_for(
                self._provider.call_mutation(entry, dict(record.changeset.canonical_args)),
                timeout=self._mutation_timeout,
            )
            ref = response.get("operation_ref") if isinstance(response, dict) else None
            op_ref = str(ref) if ref is not None else None
        except (ProviderTimeout, TimeoutError):
            outcome_reason = "provider timed out after submission; no retry was attempted"
        except ProviderError as exc:
            self._service.mark(
                proposal_id, ProposalEvent.FAIL, f"provider error: {sanitize_exception(exc)}"
            )
            return self._receipt(
                record,
                "failed",
                attempted=attempted,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason=sanitize_exception(exc),
            )

        record = self._service.mark(proposal_id, ProposalEvent.START_VERIFY, "readback started")
        outcome, observed, attempts = await self._readback(record, operation, readback_entry, entry)
        if outcome == "matches_after":
            self._service.mark(
                proposal_id, ProposalEvent.VERIFIED, "readback matched the approved change"
            )
            reason = "readback matched the approved change" + (
                f" ({outcome_reason})" if outcome_reason else ""
            )
            return self._receipt(
                record,
                "verified",
                attempted=attempted,
                op_ref=op_ref,
                verified=observed,
                catalog_revision=catalog_revision,
                reason=reason,
                readback_attempts=attempts,
            )
        if outcome == "matches_before":
            self._service.mark(
                proposal_id, ProposalEvent.FAIL, "readback shows the change was not applied"
            )
            reason = "provider state still matches the before value" + (
                f" ({outcome_reason})" if outcome_reason else ""
            )
            return self._receipt(
                record,
                "failed",
                attempted=attempted,
                op_ref=op_ref,
                verified=observed,
                catalog_revision=catalog_revision,
                reason=reason,
                readback_attempts=attempts,
            )
        self._service.mark(
            proposal_id, ProposalEvent.UNKNOWN, "readback could not prove the provider state"
        )
        reason = "provider state could not be proven within the readback budget" + (
            f" ({outcome_reason})" if outcome_reason else ""
        )
        return self._receipt(
            record,
            "unknown",
            attempted=attempted,
            op_ref=op_ref,
            verified=observed,
            catalog_revision=catalog_revision,
            reason=reason,
            readback_attempts=attempts,
        )


class ProposeChangeArgs(BaseModel):
    account_alias: str = Field(description="Configured account alias from list_accounts.")
    tool_name: str = Field(
        description="Admitted mutation tool name, e.g. google_ads__update_campaign_budget."
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


def _caller_from_runtime(runtime: Any) -> tuple[str, str]:
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = str(configurable.get("thread_id") or "local-thread")
    caller = str(configurable.get("caller_ref") or "local-user")
    return thread_id, caller


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
    return [propose_tool, execute_tool, get_tool]
