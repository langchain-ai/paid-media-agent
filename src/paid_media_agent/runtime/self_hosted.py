"""Self-hosted runtime: same components, Postgres persistence, live or fixture catalog."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from paid_media_agent.assembly import AgentComponents, build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.persistence.interfaces import DedupeStore, ThreadOwnershipStore
from paid_media_agent.persistence.memory import InMemoryDedupeStore, InMemoryThreadOwnershipStore
from paid_media_agent.runtime.local import compile_graph
from paid_media_agent.runtime.profiles import (
    RuntimeProfile,
    approval_policy_from_settings,
    fixture_profile,
    load_accounts,
    load_write_policy_file,
    resolve_write_policy,
    signer_from_settings,
)
from paid_media_agent.runtime.sandbox import build_backend
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import (
    DEFAULT_LOCAL_POLICY,
    AuthorizedToolCatalog,
    CatalogProvider,
    StaticCatalogProvider,
)
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.providers import ReadProvider, WriteProvider


@dataclass(frozen=True)
class SelfHostedRuntime:
    settings: Settings
    profile: RuntimeProfile
    catalog: AuthorizedToolCatalog
    components: AgentComponents
    graph: CompiledStateGraph[Any, Any, Any, Any]
    dedupe: DedupeStore
    threads: ThreadOwnershipStore
    persistence: str


@dataclass(frozen=True)
class LoadedCatalog:
    catalog: AuthorizedToolCatalog
    provider: CatalogProvider
    read_provider: ReadProvider | None
    write_provider: WriteProvider | None
    """Live write adapter when the catalog is live. It stays behind `WriteGate`."""


async def load_catalog(settings: Settings, *, project_root: Path | None = None) -> LoadedCatalog:
    """Live Pipeboard catalog when a token is configured, otherwise the fixture catalog.

    Direct adapters (LinkedIn, X, OpenAI Ads) join the same catalog whenever their credentials
    are configured. The reviewed write-policy file decides which live mutations are admitted.
    """
    from paid_media_agent.tools.direct import (
        CompositeReadProvider,
        direct_raw_tools,
        direct_read_providers,
    )

    direct_tools = direct_raw_tools(settings)
    direct_providers = direct_read_providers(settings)
    if settings.pipeboard_api_token is None:
        if not direct_tools:
            catalog = build_fixture_catalog()
            return LoadedCatalog(
                catalog=catalog,
                provider=StaticCatalogProvider(catalog),
                read_provider=None,
                write_provider=None,
            )
        # Fixture catalog for the Pipeboard platforms plus live direct platforms.
        from paid_media_agent.tools.catalog import build_authorized_catalog
        from paid_media_agent.tools.fixtures import (
            FIXTURE_LOCAL_POLICY,
            FixtureReadProvider,
            fixture_raw_tools,
        )

        catalog = build_authorized_catalog(
            [*fixture_raw_tools(), *direct_tools],
            policy=FIXTURE_LOCAL_POLICY,
            source="fixture+direct",
        )
        return LoadedCatalog(
            catalog=catalog,
            provider=StaticCatalogProvider(catalog),
            read_provider=CompositeReadProvider(FixtureReadProvider(), direct_providers),
            write_provider=None,
        )
    from paid_media_agent.tools.pipeboard import (
        PipeboardCatalogLoader,
        PipeboardReadProvider,
        PipeboardWriteProvider,
    )

    admitted: tuple[str, ...] = ()
    if project_root is not None:
        policy_file = load_write_policy_file(settings, project_root)
        if policy_file is not None:
            admitted = policy_file.admitted_names()
    local_policy = DEFAULT_LOCAL_POLICY.model_copy(update={"admitted_mutations": admitted})
    loader = PipeboardCatalogLoader(
        settings=settings, policy=local_policy, extra_raw_tools=direct_tools
    )
    catalog = await loader.refresh()
    return LoadedCatalog(
        catalog=catalog,
        provider=loader,
        read_provider=CompositeReadProvider(PipeboardReadProvider(loader), direct_providers),
        write_provider=PipeboardWriteProvider(loader),
    )


def _postgres_checkpointer(conn_string: str) -> BaseCheckpointSaver[Any]:
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    from psycopg.rows import dict_row

    connection = Connection.connect(
        conn_string, autocommit=True, prepare_threshold=0, row_factory=dict_row
    )
    saver = PostgresSaver(connection)
    saver.setup()
    return saver


async def build_self_hosted_runtime(
    settings: Settings,
    *,
    project_root: Path,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> SelfHostedRuntime:
    loaded = await load_catalog(settings, project_root=project_root)
    workspace = project_root / settings.paid_media_workspace_root
    backend = build_backend(settings, project_root=project_root)
    state = FixtureState()
    write_policy, issues = resolve_write_policy(settings, project_root, loaded.provider)
    live = loaded.read_provider is not None and loaded.write_provider is not None
    base = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=loaded.provider,
        name="self_hosted",
        fixture_state=state,
        approval_policy=approval_policy_from_settings(settings),
        backend=backend,
    )
    overrides: dict[str, Any] = {
        "write_policy": write_policy,
        "write_policy_issues": issues,
        "artifacts": ArtifactStore(workspace, mirror=backend.mirror),
        "workspace_root": workspace,
        "accounts": load_accounts(settings, project_root),
        "signer": signer_from_settings(settings),
    }
    if live:
        # Live catalog: live reads and the gated live write adapter. The fake is never used here.
        overrides.update(
            read_provider=loaded.read_provider,
            write_provider=loaded.write_provider,
            write_provider_is_fake=False,
        )
    else:
        overrides.update(write_provider=FakeWriteProvider(state), write_provider_is_fake=True)
    if settings.database_url is not None:
        from paid_media_agent.persistence.postgres import PostgresRepositories

        repos = PostgresRepositories(settings.database_url.get_secret_value())
        repos.setup()
        overrides.update(
            proposals=repos.proposals, approvals=repos.approvals, receipts=repos.receipts
        )
        dedupe: DedupeStore = repos.dedupe
        threads: ThreadOwnershipStore = repos.threads
        persistence = "postgres"
        if checkpointer is None:
            checkpointer = _postgres_checkpointer(settings.database_url.get_secret_value())
    else:
        dedupe = InMemoryDedupeStore()
        threads = InMemoryThreadOwnershipStore()
        persistence = "memory"
    profile = replace(base, **overrides)
    components = build_agent_components(
        settings=settings, runtime=profile, catalog=loaded.catalog, model=model
    )
    graph = compile_graph(
        components, project_root=project_root, checkpointer=checkpointer or InMemorySaver()
    )
    return SelfHostedRuntime(
        settings=settings,
        profile=profile,
        catalog=loaded.catalog,
        components=components,
        graph=graph,
        dedupe=dedupe,
        threads=threads,
        persistence=persistence,
    )
