"""MDA profile: managed backend, threads, and identity; the same assembly and policy."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from typing import Any

from paid_media_agent.assembly import AgentComponents, build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.runtime.profiles import (
    approval_policy_from_settings,
    fixture_profile,
    resolve_write_policy,
)
from paid_media_agent.runtime.self_hosted import load_catalog


def run_coroutine(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run a coroutine to completion from sync code, inside or outside an event loop.

    The CLI has no loop, so `asyncio.run` is right. LangGraph Server and `mda dev` import the
    graph factory from inside their own loop, where `asyncio.run` raises; a short-lived worker
    thread with its own loop keeps the catalog load blocking and identical on both paths.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(asyncio.run, coro).result()


def build_mda_components(
    settings: Settings,
    *,
    project_root: Path,
    loop: Callable[[Coroutine[Any, Any, Any]], Any] = run_coroutine,
) -> AgentComponents:
    """Build components for the managed runtime. Live catalog only when a token is configured."""
    loaded = loop(load_catalog(settings, project_root=project_root))
    write_policy, issues = resolve_write_policy(settings, project_root, loaded.provider)
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=loaded.provider,
        name="mda",
        approval_policy=approval_policy_from_settings(settings),
    )
    overrides: dict[str, Any] = {"write_policy": write_policy, "write_policy_issues": issues}
    if loaded.read_provider is not None and loaded.write_provider is not None:
        overrides.update(
            read_provider=loaded.read_provider,
            write_provider=loaded.write_provider,
            write_provider_is_fake=False,
        )
    profile = replace(profile, **overrides)
    return build_agent_components(settings=settings, runtime=profile, catalog=loaded.catalog)
