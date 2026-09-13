"""Governed writes: typed proposals, host-created signed approvals, one attempt, bounded readback.

The reviewed mutation set is data (`WritePolicyFile`), validated against the current catalog. The
live path is refused unless the operator has pinned the reviewed catalog revision, released the
exact tool for the canary, and enabled writes; an incident kill switch halts every execution.
"""

from __future__ import annotations

import asyncio
import hmac
import secrets
import uuid
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import jsonschema
from pydantic import BaseModel, ConfigDict

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.common import JsonValue, RiskLevel
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
from paid_media_agent.tools.catalog import (
    CatalogEntry,
    CatalogProvider,
    ToolClass,
)
from paid_media_agent.tools.providers import (
    ProviderError,
    ProviderTimeout,
    ReadProvider,
    WriteProvider,
)
from paid_media_agent.tools.write_policy import (
    WriteOperation,
    WritePolicy,
)

PROPOSE_CHANGE_TOOL = "propose_change"
EXECUTE_CHANGE_TOOL = "execute_change"
GET_PROPOSAL_TOOL = "get_proposal"
DISCOVER_WRITE_OPERATIONS_TOOL = "discover_write_operations"

DEFAULT_READBACK_ATTEMPTS = 3
DEFAULT_READBACK_SECONDS = 20.0
DEFAULT_READBACK_RETRY_SECONDS = 0.5
DEFAULT_MUTATION_TIMEOUT_SECONDS = 30.0

_STATUS_FIELDS = frozenset({"status", "state", "enabled", "paused", "active"})
_BUDGET_MARKERS = ("budget", "bid", "spend", "amount")
_BULK_MARKERS = ("ids", "items", "operations", "batch", "bulk")


def classify_risk(
    entry: CatalogEntry,
    operation: WriteOperation,
    changes: Mapping[str, JsonValue],
    before: Mapping[str, JsonValue],
) -> tuple[str, ...]:
    """Derive reviewer-facing risk facts from the operation, its schema, and the actual change."""
    name = entry.name.lower()
    flags: list[str] = []
    changed = {f.lower() for f in changes}
    if changed & _STATUS_FIELDS or any(
        m in name for m in ("activate", "enable", "pause", "archive", "status")
    ):
        flags.append("status_flip")
        for field, value in changes.items():
            if field.lower() in _STATUS_FIELDS and str(value).upper() in (
                "ENABLED",
                "ACTIVE",
                "RUNNING",
                "LIVE",
            ):
                flags.append("starts_delivery")
    for field, value in changes.items():
        if any(m in field.lower() for m in _BUDGET_MARKERS):
            flags.append("budget_delta")
            try:
                previous = Decimal(str(before.get(field)))
                proposed = Decimal(str(value))
                if proposed > previous:
                    flags.append("budget_increase")
            except (InvalidOperation, ValueError, TypeError):
                flags.append("budget_unverified_before")
    if any(m in name for m in ("publish", "activate", "enable", "lead_form")):
        flags.append("publishes_live")
    if any(m in name for m in ("permission", "invitation", "account_slots", "member")):
        flags.append("access_change")
    if entry.destructive_hint is True or any(m in name for m in ("delete", "remove")):
        flags.append("destructive_change")
    if any(m in name for m in ("audience", "conversion_event", "customer_list", "upload", "user")):
        flags.append("sensitive_data_transfer")
    if any(m in name for m in ("rule", "schedule", "automation")):
        flags.append("standing_automation")
    properties = entry.input_schema.get("properties", {})
    if isinstance(properties, Mapping) and any(
        any(m in f.lower() for m in _BULK_MARKERS) for f in properties
    ):
        flags.append("bulk_capable")
    if operation.risk is RiskLevel.HIGH:
        flags.append("policy_high_risk")
    return tuple(dict.fromkeys(flags))


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
    """Execution gate. Fakes need only the kill switch to be clear; live providers need every flag.

    A live mutation requires, in this order: kill switch absent, `PAID_MEDIA_WRITES_ENABLED=true`,
    the operator-pinned catalog revision equal to the current one, and the exact tool released for
    the canary. Tests never set those values, so no automated path reaches a live mutation.
    """

    def __init__(
        self,
        *,
        writes_enabled: bool,
        provider_is_fake: bool,
        kill_switch_path: Path | None = None,
        released_catalog_revision: str | None = None,
        canary_tools: frozenset[str] = frozenset(),
        current_revision: Callable[[], str] | None = None,
    ) -> None:
        self.writes_enabled = writes_enabled
        self.provider_is_fake = provider_is_fake
        self.kill_switch_path = kill_switch_path
        self.released_catalog_revision = released_catalog_revision
        self.canary_tools = canary_tools
        self._current_revision = current_revision

    def kill_switch_engaged(self) -> bool:
        return self.kill_switch_path is not None and self.kill_switch_path.exists()

    def check(self, tool_name: str) -> None:
        if self.kill_switch_engaged():
            raise WriteDenied(
                "kill_switch",
                f"{self.kill_switch_path} exists; remove it after the incident review",
            )
        if self.provider_is_fake:
            return
        if not self.writes_enabled:
            raise WriteDenied("writes_disabled", "PAID_MEDIA_WRITES_ENABLED is false")
        if self.released_catalog_revision is None:
            raise WriteDenied(
                "live_writes_not_released", "PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION is not pinned"
            )
        current = self._current_revision() if self._current_revision else None
        if current != self.released_catalog_revision:
            raise WriteDenied(
                "stale_catalog", "current catalog revision differs from the reviewed revision"
            )
        if tool_name not in self.canary_tools:
            raise WriteDenied(
                "tool_not_released", f"{tool_name} is not in PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS"
            )

    def describe(self) -> str:
        if self.provider_is_fake:
            return "fake provider (fixture); live writes unreachable"
        state = "enabled" if self.writes_enabled else "disabled"
        pinned = self.released_catalog_revision or "unpinned"
        return f"live provider; writes {state}; reviewed revision {pinned}; canary tools {len(self.canary_tools)}"


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

    @property
    def approvals(self) -> ApprovalRepository:
        return self._approvals

    def admitted_operations(self) -> list[dict[str, JsonValue]]:
        """Operations the current catalog can honor, for `discover_write_operations`."""
        catalog = self._catalog_provider.current()
        rows: list[dict[str, JsonValue]] = []
        for op in self._write_policy.operations:
            entry = catalog.get(op.tool_name)
            if entry is None or entry.tool_class is not ToolClass.MUTATION:
                continue
            rows.append(
                {
                    "tool_name": op.tool_name,
                    "platform": entry.platform.value,
                    "description": entry.description[:200],
                    "target_arg": op.target_arg,
                    "editable_fields": list(op.editable_fields),
                    "units": dict(op.units),
                    "risk": op.risk.value,
                    "readback_tool": op.readback_tool,
                }
            )
        return rows

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
        if not isinstance(target_ref, str) or not target_ref.strip():
            raise WriteDenied("invalid_target")
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
        before_values = {f: _json_ready(state.get(operation.readback_fields[f])) for f in changes}
        before = tuple(
            FieldValue(field=f, value=v, unit=operation.units.get(f))
            for f, v in before_values.items()
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
                schema_hash=entry.schema_hash,
                policy_digest=operation.digest(),
                risk_flags=classify_risk(entry, operation, changes, before_values),
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
        self._save(record)
        return record

    def get(self, proposal_id: UUID) -> ProposalRecord | None:
        return self._proposals.get(proposal_id)

    def belongs_to(self, proposal_id: UUID, thread_id: str) -> bool:
        record = self._proposals.get(proposal_id)
        return record is not None and record.changeset.thread_id == thread_id

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
        before_values = {fv.field: fv.value for fv in before}
        changeset = stamp_digest(
            record.changeset.model_copy(
                update={
                    "revision": record.changeset.revision + 1,
                    "canonical_args": args,
                    "before": before,
                    "after": after,
                    "catalog_revision": catalog_revision,
                    "schema_hash": entry.schema_hash,
                    "policy_digest": operation.digest(),
                    "risk_flags": classify_risk(entry, operation, changes, before_values),
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
        self._save(updated, expected=record)
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
        self._save(updated, expected=record)
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
        self._save(
            record.model_copy(
                update={
                    "history": (*record.history, f"{now.isoformat()} approved by {approver_ref}")
                }
            ),
            expected=record,
        )
        self._approvals.save(claim)
        return claim

    def _save(self, record: ProposalRecord, *, expected: ProposalRecord | None = None) -> None:
        if not self._proposals.save(record, expected=expected):
            raise WriteDenied("proposal_changed", "reload the current proposal before retrying")

    def _require(self, proposal_id: UUID) -> ProposalRecord:
        record = self._proposals.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        return record

    def mark(
        self,
        proposal_id: UUID,
        event: ProposalEvent,
        note: str,
        *,
        expected: ProposalRecord | None = None,
    ) -> ProposalRecord:
        record = expected if expected is not None else self._require(proposal_id)
        if record.changeset.proposal_id != proposal_id:
            raise WriteDenied("unknown_proposal")
        try:
            state_value = transition(record.state, event)
        except InvalidTransition as exc:
            raise WriteDenied("invalid_transition", str(exc)) from None
        updated = record.model_copy(
            update={"state": state_value, "history": (*record.history, note)}
        )
        self._save(updated, expected=record)
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

    @property
    def gate(self) -> WriteGate:
        return self._gate

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
        if cs.schema_hash and entry.schema_hash != cs.schema_hash:
            raise WriteDenied("stale_catalog", "mutation tool schema changed since the proposal")
        operation = self._write_policy.get(cs.tool_name)
        if operation is None:
            raise WriteDenied("no_write_policy")
        if cs.policy_digest and operation.digest() != cs.policy_digest:
            raise WriteDenied("stale_policy", "write policy changed since the proposal")
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
        acknowledged: bool,
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
            provider_acknowledged=acknowledged,
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
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._readback_seconds
        attempts = 0
        observed: tuple[FieldValue, ...] = ()
        while attempts < self._readback_attempts:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            attempts += 1
            try:
                state = await asyncio.wait_for(
                    read_entity_state(self._read_provider, readback_entry, read_args, operation),
                    timeout=remaining,
                )
            except TimeoutError:
                return "unproven", observed, attempts
            except ProviderError:
                pass
            else:
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
            remaining = deadline - loop.time()
            if attempts < self._readback_attempts and remaining > 0:
                await self._sleep(min(DEFAULT_READBACK_RETRY_SECONDS, remaining))
        if observed and all(
            values_equal({fv.field: fv.value for fv in observed}.get(f), v)
            for f, v in before.items()
        ):
            return "matches_before", observed, attempts
        return "unproven", observed, attempts

    def _rejected(self, record: ProposalRecord, catalog_revision: str, reason: str) -> WriteReceipt:
        return self._receipt(
            record,
            "rejected",
            attempted=False,
            acknowledged=False,
            op_ref=None,
            verified=(),
            catalog_revision=catalog_revision,
            reason=reason,
        )

    async def execute(self, proposal_id: UUID) -> WriteReceipt:
        record = self._service.get(proposal_id)
        if record is None:
            raise WriteDenied("unknown_proposal")
        catalog_revision = self._catalog_provider.current().revision
        if record.state is not ProposalState.AWAITING_APPROVAL:
            receipt = self._receipts.get(proposal_id)
            if receipt is not None and receipt.revision == record.changeset.revision:
                return receipt
            raise WriteDenied("not_awaiting_approval", f"proposal is {record.state.value}")
        claim = self._approvals.latest_unused(
            record.changeset.proposal_id, record.changeset.revision
        )
        if claim is None:
            raise WriteDenied("approval_required", "no valid approval claim for this revision")
        try:
            self._verify_claim(record, claim)
            entry, operation, readback_entry, catalog_revision = self._verify_catalog(record)
            self._gate.check(record.changeset.tool_name)
        except WriteDenied as exc:
            self._service.mark(
                proposal_id,
                ProposalEvent.REJECT,
                f"{self._clock().isoformat()} execution refused: {exc.reason}",
                expected=record,
            )
            return self._rejected(
                record, catalog_revision, f"{exc.reason}: {exc.detail}".rstrip(": ")
            )
        record = self._service.mark(
            proposal_id,
            ProposalEvent.APPROVE,
            f"{self._clock().isoformat()} executing with claim {claim.claim_id}",
            expected=record,
        )
        if not self._approvals.mark_used(claim.claim_id):
            self._service.mark(
                proposal_id, ProposalEvent.FAIL, "approval replay refused", expected=record
            )
            return self._rejected(record, catalog_revision, "approval already used")
        arguments = dict(record.changeset.canonical_args)
        if operation.validate_only_arg is not None:
            try:
                await asyncio.wait_for(
                    self._provider.call_mutation(
                        entry, {**arguments, operation.validate_only_arg: True}
                    ),
                    timeout=self._mutation_timeout,
                )
            except (ProviderError, TimeoutError) as exc:
                self._service.mark(
                    proposal_id,
                    ProposalEvent.FAIL,
                    f"validation refused: {sanitize_exception(exc)}",
                )
                return self._receipt(
                    record,
                    "failed",
                    attempted=False,
                    acknowledged=False,
                    op_ref=None,
                    verified=(),
                    catalog_revision=catalog_revision,
                    reason=f"provider validation refused the payload: {sanitize_exception(exc)}",
                )
        if operation.idempotency_arg is not None:
            arguments[operation.idempotency_arg] = (
                f"{record.changeset.proposal_id}:{record.changeset.revision}"
            )
        attempted = True
        acknowledged = False
        op_ref: str | None = None
        outcome_reason = ""
        try:
            response = await asyncio.wait_for(
                self._provider.call_mutation(entry, arguments), timeout=self._mutation_timeout
            )
            acknowledged = True
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
                acknowledged=False,
                op_ref=None,
                verified=(),
                catalog_revision=catalog_revision,
                reason=sanitize_exception(exc),
            )

        record = self._service.mark(proposal_id, ProposalEvent.START_VERIFY, "readback started")
        outcome, observed, attempts = await self._readback(record, operation, readback_entry, entry)
        suffix = f" ({outcome_reason})" if outcome_reason else ""
        if outcome == "matches_after":
            self._service.mark(
                proposal_id, ProposalEvent.VERIFIED, "readback matched the approved change"
            )
            return self._receipt(
                record,
                "verified",
                attempted=attempted,
                acknowledged=acknowledged,
                op_ref=op_ref,
                verified=observed,
                catalog_revision=catalog_revision,
                reason="readback matched the approved change" + suffix,
                readback_attempts=attempts,
            )
        if outcome == "matches_before":
            self._service.mark(
                proposal_id, ProposalEvent.FAIL, "readback shows the change was not applied"
            )
            return self._receipt(
                record,
                "failed",
                attempted=attempted,
                acknowledged=acknowledged,
                op_ref=op_ref,
                verified=observed,
                catalog_revision=catalog_revision,
                reason="provider state still matches the before value" + suffix,
                readback_attempts=attempts,
            )
        self._service.mark(
            proposal_id, ProposalEvent.UNKNOWN, "readback could not prove the provider state"
        )
        return self._receipt(
            record,
            "unknown",
            attempted=attempted,
            acknowledged=acknowledged,
            op_ref=op_ref,
            verified=observed,
            catalog_revision=catalog_revision,
            reason="provider state could not be proven within the readback budget" + suffix,
            readback_attempts=attempts,
        )
