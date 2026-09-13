"""Local compilation of the shared components: the fixture demo, tests, and the CLI.

Managed Deep Agents compiles the same components in production. Here `create_deep_agent` does it
with the repository as the model's filesystem and an in-memory checkpointer.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends import FilesystemBackend
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph

from paid_media_agent.assembly import AgentComponents, build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.runtime.mda import configured_profile
from paid_media_agent.runtime.profiles import RuntimeProfile, fixture_profile
from paid_media_agent.tools.catalog import AuthorizedToolCatalog, StaticCatalogProvider
from paid_media_agent.tools.fixtures import FixtureState, build_fixture_catalog


def filesystem_permissions() -> list[FilesystemPermission]:
    """Hide secrets and coding-agent files; keep runtime skills read-only."""
    return [
        FilesystemPermission(
            operations=["read", "write"],
            paths=[
                "/.env",
                "/.env.*",
                "/.venv/**",
                "/.git/**",
                "/.mda/**",
                "/.agents/**",
                "/.claude/**",
            ],
            mode="deny",
        ),
        FilesystemPermission(operations=["write"], paths=["/workspace/skills/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/workspace/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/**"], mode="deny"),
    ]


@dataclass(frozen=True)
class LocalRuntime:
    settings: Settings
    profile: RuntimeProfile
    catalog: AuthorizedToolCatalog
    components: AgentComponents
    graph: CompiledStateGraph[Any, Any, Any, Any]
    checkpointer: BaseCheckpointSaver[Any]


def compile_graph(
    components: AgentComponents,
    *,
    project_root: Path,
    checkpointer: BaseCheckpointSaver[Any] | None,
    name: str = "paid-media-agent",
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile the shared components with Deep Agents over the repository filesystem."""
    return create_deep_agent(
        components.model,
        list(components.tools),
        system_prompt=components.system_prompt,
        middleware=list(components.middleware),
        skills=list(components.skills),
        permissions=filesystem_permissions(),
        backend=FilesystemBackend(root_dir=project_root, virtual_mode=True),
        interrupt_on=dict(components.interrupt_on) or None,
        checkpointer=checkpointer,
        name=name,
    )


def build_local_runtime(
    settings: Settings,
    *,
    project_root: Path,
    model: BaseChatModel,
    catalog: AuthorizedToolCatalog | None = None,
    catalog_provider: StaticCatalogProvider | None = None,
    profile: RuntimeProfile | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    fixture_state: FixtureState | None = None,
    workspace_root: Path | None = None,
) -> LocalRuntime:
    """Fixture catalog and fake writes with the model you pass: the demo and the test suite."""
    resolved_catalog = catalog or build_fixture_catalog()
    provider = catalog_provider or StaticCatalogProvider(resolved_catalog)
    resolved_profile = profile or fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=provider,
        fixture_state=fixture_state,
        workspace_root=workspace_root,
    )
    components = build_agent_components(
        settings=settings, runtime=resolved_profile, catalog=resolved_catalog, model=model
    )
    saver = checkpointer or InMemorySaver()
    graph = compile_graph(components, project_root=project_root, checkpointer=saver)
    return LocalRuntime(
        settings=settings,
        profile=resolved_profile,
        catalog=resolved_catalog,
        components=components,
        graph=graph,
        checkpointer=saver,
    )


def build_configured_runtime(
    settings: Settings, *, project_root: Path, model: BaseChatModel | None = None
) -> LocalRuntime:
    """The deployment's profile compiled locally: live catalog when credentials exist.

    `paid-media-agent ask` and `report` use this, so a local answer comes from the same accounts,
    policy, and tools the hosted agent has. The write gate still decides whether a live mutation
    can run; nothing here loosens it.
    """
    profile, loaded = configured_profile(settings, project_root=project_root)
    components = build_agent_components(
        settings=settings, runtime=profile, catalog=loaded.catalog, model=model
    )
    saver = InMemorySaver()
    graph = compile_graph(components, project_root=project_root, checkpointer=saver)
    return LocalRuntime(
        settings=settings,
        profile=profile,
        catalog=loaded.catalog,
        components=components,
        graph=graph,
        checkpointer=saver,
    )
