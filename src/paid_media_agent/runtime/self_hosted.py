"""Self-hosted runtime: same components, Postgres persistence, live or fixture catalog."""

from __future__ import annotations

from dataclasses import dataclass
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
    signer_from_settings,
)
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import (
    AuthorizedToolCatalog,
    CatalogProvider,
    StaticCatalogProvider,
)
from paid_media_agent.tools.fixtures import FakeWriteProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.writes import fixture_write_policy


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


async def load_catalog(settings: Settings) -> tuple[AuthorizedToolCatalog, CatalogProvider, Any]:
    """Live Pipeboard catalog when a token is configured, otherwise the fixture catalog."""
    if settings.pipeboard_api_token is None:
        catalog = build_fixture_catalog()
        return catalog, StaticCatalogProvider(catalog), None
    from paid_media_agent.tools.pipeboard import (  # noqa: PLC0415
        PipeboardCatalogLoader,
        PipeboardReadProvider,
    )

    loader = PipeboardCatalogLoader(settings=settings)
    catalog = await loader.refresh()
    return catalog, loader, PipeboardReadProvider(loader)


async def build_self_hosted_runtime(
    settings: Settings,
    *,
    project_root: Path,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> SelfHostedRuntime:
    catalog, provider, live_reads = await load_catalog(settings)
    workspace = project_root / settings.paid_media_workspace_root
    state = FixtureState()
    if settings.database_url is not None:
        from paid_media_agent.persistence.postgres import PostgresRepositories  # noqa: PLC0415

        repos = PostgresRepositories(settings.database_url.get_secret_value())
        repos.setup()
        profile = RuntimeProfile(
            name="self_hosted",
            workspace_root=workspace,
            artifacts=ArtifactStore(workspace),
            accounts=load_accounts(settings, project_root),
            catalog_provider=provider,
            read_provider=live_reads
            if live_reads is not None
            else fixture_profile(
                settings, project_root=project_root, catalog_provider=provider, fixture_state=state
            ).read_provider,
            # Live provider mutations are not released. The fake keeps the governed flow demonstrable.
            write_provider=FakeWriteProvider(state),
            write_provider_is_fake=True,
            write_policy=fixture_write_policy(),
            approval_policy=approval_policy_from_settings(settings),
            signer=signer_from_settings(settings),
            proposals=repos.proposals,
            approvals=repos.approvals,
            receipts=repos.receipts,
            skills_root=project_root,
        )
        dedupe: DedupeStore = repos.dedupe
        threads: ThreadOwnershipStore = repos.threads
        persistence = "postgres"
        if checkpointer is None:
            from langgraph.checkpoint.postgres import PostgresSaver  # noqa: PLC0415

            saver = PostgresSaver.from_conn_string(
                settings.database_url.get_secret_value()
            ).__enter__()
            saver.setup()
            checkpointer = saver
    else:
        profile = fixture_profile(
            settings,
            project_root=project_root,
            catalog_provider=provider,
            name="self_hosted",
            fixture_state=state,
            approval_policy=approval_policy_from_settings(settings),
        )
        if live_reads is not None:
            profile = RuntimeProfile(**{**profile.__dict__, "read_provider": live_reads})
        dedupe = InMemoryDedupeStore()
        threads = InMemoryThreadOwnershipStore()
        persistence = "memory"
    components = build_agent_components(
        settings=settings, runtime=profile, catalog=catalog, model=model
    )
    graph = compile_graph(
        components, project_root=project_root, checkpointer=checkpointer or InMemorySaver()
    )
    return SelfHostedRuntime(
        settings=settings,
        profile=profile,
        catalog=catalog,
        components=components,
        graph=graph,
        dedupe=dedupe,
        threads=threads,
        persistence=persistence,
    )
