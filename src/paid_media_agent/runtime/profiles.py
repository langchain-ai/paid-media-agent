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
from paid_media_agent.reports.render import HostPdfEngine, PdfEngine
from paid_media_agent.runtime.sandbox import Backend
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import CatalogProvider
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureReadProvider, FixtureState
from paid_media_agent.tools.providers import ReadProvider, WriteProvider
from paid_media_agent.tools.write_policy import (
    PolicyIssue,
    WritePolicy,
    WritePolicyFile,
    fixture_write_policy,
)
from paid_media_agent.tools.writes import ApprovalPolicy, ApprovalSigner, WriteGate

ProfileName = Literal["local", "mda", "self_hosted"]
RunMode = Literal["conversation"]
"""Reserved for a future read-only mode; every current entry point is a conversation."""


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
    write_policy_issues: tuple[PolicyIssue, ...] = field(default_factory=tuple)
    backend: Backend | None = None
    """None means the repository filesystem; see `runtime.sandbox.build_backend`."""

    @property
    def pdf_engine(self) -> PdfEngine:
        return self.backend.pdf_engine if self.backend is not None else HostPdfEngine()

    def write_gate(self, settings: Settings) -> WriteGate:
        kill_switch = settings.paid_media_kill_switch_path
        if not kill_switch.is_absolute():
            kill_switch = (self.skills_root or Path.cwd()) / kill_switch
        provider = self.catalog_provider
        return WriteGate(
            writes_enabled=settings.paid_media_writes_enabled,
            provider_is_fake=self.write_provider_is_fake,
            kill_switch_path=kill_switch,
            released_catalog_revision=settings.paid_media_live_write_catalog_revision,
            canary_tools=settings.live_write_canary_tools(),
            current_revision=lambda: provider.current().revision,
        )


def load_accounts(settings: Settings, project_root: Path) -> AccountRegistry:
    path = settings.paid_media_account_config_path
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return AccountRegistry()
    return AccountRegistry.from_toml(path)


def load_write_policy_file(settings: Settings, project_root: Path) -> WritePolicyFile | None:
    path = settings.paid_media_write_policy_path
    if not path.is_absolute():
        path = project_root / path
    if not path.exists():
        return None
    return WritePolicyFile.from_toml(path)


def resolve_write_policy(
    settings: Settings, project_root: Path, catalog_provider: CatalogProvider
) -> tuple[WritePolicy, tuple[PolicyIssue, ...]]:
    """Reviewed policy file validated against the current catalog; fixture policy as fallback."""
    policy_file = load_write_policy_file(settings, project_root)
    if policy_file is None:
        return fixture_write_policy(), ()
    return policy_file.validate_against(catalog_provider.current())


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
    backend: Backend | None = None,
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
        artifacts=ArtifactStore(root, mirror=backend.mirror if backend else None),
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
        backend=backend,
    )
