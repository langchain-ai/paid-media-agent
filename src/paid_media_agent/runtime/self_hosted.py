"""Self-hosted runtime: the configured profile, Postgres when configured, and a compiled graph.

Managed Deep Agents is the one-command deployment. This is the path for teams that want their own
API, database, and Slack app: the same components `agent.py` hands to MDA, compiled with
`create_deep_agent`, with proposals, approval claims, receipts, dedupe keys, thread ownership, and
checkpoints in Postgres when `DATABASE_URL` is set and in memory otherwise.

Build it inside the event loop that will serve requests (`serve` and `slack` do), because the
Postgres checkpointer is asynchronous and bound to that loop.
"""

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
from paid_media_agent.runtime.mda import configured_profile
from paid_media_agent.runtime.profiles import RuntimeProfile
from paid_media_agent.tools.catalog import AuthorizedToolCatalog


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


async def _postgres_checkpointer(conn_string: str) -> BaseCheckpointSaver[Any]:
    """The async saver over a pool. The graph is always driven with `ainvoke`, and the API and
    the Slack adapter run in one event loop, so every checkpoint read and write shares it."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool

    pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
        conn_string,
        min_size=1,
        max_size=4,
        open=False,
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    )
    await pool.open()
    saver = AsyncPostgresSaver(pool)
    await saver.setup()
    return saver


async def build_self_hosted_runtime(
    settings: Settings,
    *,
    project_root: Path,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> SelfHostedRuntime:
    profile, loaded = configured_profile(settings, project_root=project_root, name="self_hosted")
    if settings.database_url is not None:
        from paid_media_agent.persistence.postgres import PostgresRepositories

        repos = PostgresRepositories(settings.database_url.get_secret_value())
        repos.setup()
        profile = replace(
            profile, proposals=repos.proposals, approvals=repos.approvals, receipts=repos.receipts
        )
        dedupe: DedupeStore = repos.dedupe
        threads: ThreadOwnershipStore = repos.threads
        persistence = "postgres"
        if checkpointer is None:
            checkpointer = await _postgres_checkpointer(settings.database_url.get_secret_value())
    else:
        dedupe = InMemoryDedupeStore()
        threads = InMemoryThreadOwnershipStore()
        persistence = "memory"
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
