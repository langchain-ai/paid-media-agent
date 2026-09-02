from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from paid_media_agent.domain.common import Platform, RiskLevel
from paid_media_agent.domain.proposals import (
    ChangeSet,
    FieldValue,
    InvalidTransition,
    ProposalEvent,
    ProposalState,
    compute_payload_digest,
    stamp_digest,
    transition,
)
from paid_media_agent.middleware.redaction import redact, sanitize_exception
from paid_media_agent.tools.artifacts import ArtifactError, ArtifactStore
from paid_media_agent.tools.writes import ApprovalSigner


def _changeset(**overrides: object) -> ChangeSet:
    base = dict(
        proposal_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        revision=1,
        platform=Platform.GOOGLE_ADS,
        account_ref="demo-google",
        tool_name="google_ads__update_campaign_budget",
        target_ref="g-103",
        canonical_args={
            "customer_id": "fixture-google-0001",
            "campaign_id": "g-103",
            "daily_budget": 240,
        },
        before=(FieldValue(field="daily_budget", value=300.0),),
        after=(FieldValue(field="daily_budget", value=240),),
        reason="test",
        risk=RiskLevel.MEDIUM,
        catalog_revision="rev1",
        payload_digest="",
        requester_ref="local-user",
        thread_id="t1",
    )
    base.update(overrides)
    return stamp_digest(ChangeSet(**base))  # type: ignore[arg-type]


def test_digest_is_stable_and_binds_payload_not_prose() -> None:
    a = _changeset()
    b = _changeset(reason="different prose", measurement_plan="x")
    assert a.payload_digest == b.payload_digest
    assert a.payload_digest == compute_payload_digest(a.digest_material())
    assert (
        _changeset(
            canonical_args={
                "customer_id": "fixture-google-0001",
                "campaign_id": "g-103",
                "daily_budget": 241,
            }
        ).payload_digest
        != a.payload_digest
    )
    assert _changeset(account_ref="demo-meta").payload_digest != a.payload_digest
    assert _changeset(revision=2).payload_digest != a.payload_digest
    assert _changeset(requester_ref="someone-else").payload_digest != a.payload_digest


def test_state_machine_rejects_invalid_transitions() -> None:
    state = transition(ProposalState.DRAFT, ProposalEvent.PROPOSE)
    state = transition(state, ProposalEvent.REQUEST_APPROVAL)
    assert state is ProposalState.AWAITING_APPROVAL
    assert transition(state, ProposalEvent.EDIT) is ProposalState.REVISED
    executing = transition(state, ProposalEvent.APPROVE)
    with pytest.raises(InvalidTransition):
        transition(executing, ProposalEvent.APPROVE)
    with pytest.raises(InvalidTransition):
        transition(ProposalState.VERIFIED, ProposalEvent.EDIT)
    assert (
        transition(transition(executing, ProposalEvent.START_VERIFY), ProposalEvent.UNKNOWN)
        is ProposalState.UNKNOWN
    )


def test_signer_rejects_tampered_material_and_short_keys() -> None:
    signer = ApprovalSigner(b"0123456789abcdef0123")
    sig = signer.sign("a|b|c")
    assert signer.verify("a|b|c", sig)
    assert not signer.verify("a|b|d", sig)
    assert not ApprovalSigner(b"another-key-with-16-bytes!").verify("a|b|c", sig)
    with pytest.raises(ValueError):
        ApprovalSigner(b"short")


def test_redaction_masks_credentials_and_bounded_errors() -> None:
    text = "Authorization: Bearer abc.def-ghi xoxb-123456789-abcdefgh sk-ant-abcdefghijklmnopqrstuvwxyz postgres://u:p@h/db api_key=ABCDEFGHIJKLMNOP"
    cleaned = redact(text, secrets=["my-secret-token-value"])
    for needle in ("Bearer abc", "xoxb-", "sk-ant-", "postgres://", "ABCDEFGHIJKLMNOP"):
        assert needle not in cleaned, needle
    assert "my-secret" not in redact(
        "token my-secret-token-value here", secrets=["my-secret-token-value"]
    )
    message = sanitize_exception(RuntimeError("boom\nline2 " + "x" * 1000), secrets=[])
    assert "\n" not in message and len(message) <= 400 and message.startswith("RuntimeError")


def test_artifact_store_enforces_ids_and_hashes(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "ws")
    meta = store.write_json("analysis", {"a": 1}, schema_version="x/1")
    assert (tmp_path / "ws" / "analysis" / f"{meta.artifact_id}.json").exists()
    assert store.read(meta.artifact_id).payload == {"a": 1}
    with pytest.raises(ArtifactError):
        store.read("../../etc/passwd")
    with pytest.raises(ArtifactError):
        store.read("art_0000000000000000")
    path = store.absolute_path(meta)
    envelope = json.loads(path.read_text())
    envelope["payload"]["a"] = 2
    path.write_text(json.dumps(envelope))
    with pytest.raises(ArtifactError, match="hash"):
        store.read(meta.artifact_id)


def test_claim_material_includes_every_binding_field() -> None:
    from paid_media_agent.domain.proposals import ApprovalClaim

    now = datetime(2026, 9, 1, tzinfo=UTC)
    claim = ApprovalClaim(
        claim_id=uuid.uuid4(),
        proposal_id=uuid.uuid4(),
        revision=1,
        payload_digest="d",
        account_ref="a",
        tool_name="t",
        requester_ref="r",
        approver_ref="p",
        approved_at=now,
        expires_at=now,
        nonce="n",
        signature="",
    )
    material = claim.signing_material()
    for part in (str(claim.claim_id), str(claim.proposal_id), "d", "a", "t", "r", "p", "n"):
        assert part in material
