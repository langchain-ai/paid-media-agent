"""The configured profile: live catalog when credentials exist, fixtures otherwise.

`agent.py` hands these components to Managed Deep Agents, which supplies the checkpointer, the
per-thread sandbox, identity, schedules, and Slack. The CLI compiles the same profile locally for
`ask` and `report`, and the self-hosted runtime compiles it behind its own API, so what you try
on your machine is what either deployment runs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from paid_media_agent.assembly import AgentComponents, build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.runtime.catalog import LoadedCatalog, load_catalog
from paid_media_agent.runtime.profiles import (
    ProfileName,
    RuntimeProfile,
    approval_policy_from_settings,
    fixture_profile,
    resolve_write_policy,
)

Loop = Callable[[Coroutine[Any, Any, Any]], Any]


def run_coroutine(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion from sync code, inside or outside an event loop.

    The CLI has no loop, so `asyncio.run` is right. `mda dev` imports `agent.py` from inside its
    own loop, where `asyncio.run` raises; a short-lived worker thread with its own loop keeps the
    catalog load blocking and identical on both paths.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def configured_profile(
    settings: Settings,
    *,
    project_root: Path,
    loop: Loop = run_coroutine,
    name: ProfileName = "mda",
) -> tuple[RuntimeProfile, LoadedCatalog]:
    """The profile every entry point runs: live providers only when their credentials exist."""
    loaded = loop(load_catalog(settings, project_root=project_root))
    write_policy, issues = resolve_write_policy(settings, project_root, loaded.provider)
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=loaded.provider,
        name=name,
        approval_policy=approval_policy_from_settings(settings),
    )
    overrides: dict[str, Any] = {"write_policy": write_policy, "write_policy_issues": issues}
    if loaded.read_provider is not None:
        overrides["read_provider"] = loaded.read_provider
    if loaded.live:
        # Live catalog: live reads and the gated live write adapter. The fake is never used here.
        overrides.update(
            read_provider=loaded.read_provider,
            write_provider=loaded.write_provider,
            write_provider_is_fake=False,
        )
    return replace(profile, **overrides), loaded


def build_mda_components(
    settings: Settings, *, project_root: Path, loop: Loop = run_coroutine
) -> AgentComponents:
    """Components for `define_deep_agent`. Managed Deep Agents owns everything around them."""
    profile, loaded = configured_profile(settings, project_root=project_root, loop=loop)
    return build_agent_components(settings=settings, runtime=profile, catalog=loaded.catalog)
