"""Runtime profile: what an adapter supplies to the shared assembly."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from paid_media_agent.config import AccountRegistry, Settings
from paid_media_agent.persistence.interfaces import (
    ApprovalRepository,
    ProposalRepository,
    ReceiptRepository,
)
from paid_media_agent.persistence.memory import (
    InMemoryApprovalRepository,
    InMemoryProposalRepository,
    InMemoryReceiptRepository,
)
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import CatalogProvider
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureReadProvider, FixtureState
from paid_media_agent.tools.providers import ReadProvider, WriteProvider
from paid_media_agent.tools.writes import (
    ApprovalPolicy,
    ApprovalSigner,
    WriteGate,
    WritePolicy,
    fixture_write_policy,
)

ProfileName = Literal["local", "mda", "self_hosted"]
RunMode = Literal["conversation", "schedule"]


@dataclass(frozen=True)
class RuntimeProfile:
    """Everything outside the shared core: storage, providers, identity policy, and paths."""

    name: ProfileName
    workspace_root: Path
    artifacts: ArtifactStore
    accounts: AccountRegistry
    catalog_provider: CatalogProvider
    read_provider: ReadProvider
    write_provider: WriteProvider
    write_provider_is_fake: bool
    write_policy: WritePolicy
    approval_policy: ApprovalPolicy
    signer: ApprovalSigner
    proposals: ProposalRepository
    approvals: ApprovalRepository
    receipts: ReceiptRepository
    run_mode: RunMode = "conversation"
    skills_root: Path | None = None
    extra_secrets: tuple[str, ...] = field(default_factory=tuple)

    def write_gate(self, settings: Settings) -> WriteGate:
        return WriteGate(
            writes_enabled=settings.paid_media_writes_enabled,
            provider_is_fake=self.write_provider_is_fake,
        )


def load_accounts(settings: Settings, project_root: Path) -> AccountRegistry:
    path = settings.paid_media_account_config_path
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return AccountRegistry()
    return AccountRegistry.from_toml(path)


def signer_from_settings(settings: Settings) -> ApprovalSigner:
    if settings.paid_media_approval_signing_key is not None:
        return ApprovalSigner(
            settings.paid_media_approval_signing_key.get_secret_value().encode("utf-8")
        )
    return ApprovalSigner.ephemeral()


def approval_policy_from_settings(
    settings: Settings, *, default_approvers: frozenset[str] = frozenset()
) -> ApprovalPolicy:
    approvers = settings.approver_refs() or default_approvers
    return ApprovalPolicy(
        approver_refs=approvers,
        allow_self_approval=settings.paid_media_allow_self_approval,
        ttl_seconds=settings.paid_media_approval_ttl_seconds,
    )


def fixture_profile(
    settings: Settings,
    *,
    project_root: Path,
    catalog_provider: CatalogProvider,
    name: ProfileName = "local",
    workspace_root: Path | None = None,
    fixture_state: FixtureState | None = None,
    write_provider: FakeWriteProvider | None = None,
    approval_policy: ApprovalPolicy | None = None,
    proposals: ProposalRepository | None = None,
    approvals: ApprovalRepository | None = None,
    receipts: ReceiptRepository | None = None,
    run_mode: RunMode = "conversation",
) -> RuntimeProfile:
    """Fixture-backed profile. The write provider is always the in-memory fake."""
    state = fixture_state or FixtureState()
    root = workspace_root or (project_root / settings.paid_media_workspace_root)
    return RuntimeProfile(
        name=name,
        workspace_root=root,
        artifacts=ArtifactStore(root),
        accounts=load_accounts(settings, project_root),
        catalog_provider=catalog_provider,
        read_provider=FixtureReadProvider(state),
        write_provider=write_provider or FakeWriteProvider(state),
        write_provider_is_fake=True,
        write_policy=fixture_write_policy(),
        approval_policy=approval_policy
        or approval_policy_from_settings(settings, default_approvers=frozenset({"local-user"})),
        signer=signer_from_settings(settings),
        proposals=proposals or InMemoryProposalRepository(),
        approvals=approvals or InMemoryApprovalRepository(),
        receipts=receipts or InMemoryReceiptRepository(),
        run_mode=run_mode,
        skills_root=project_root,
    )
