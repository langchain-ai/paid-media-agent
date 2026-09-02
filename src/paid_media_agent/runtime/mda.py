"""MDA profile: managed backend, threads, and identity; the same assembly and policy."""

from __future__ import annotations

from collections.abc import Callable
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


def build_mda_components(
    settings: Settings, *, project_root: Path, loop: Callable[[Any], Any]
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
