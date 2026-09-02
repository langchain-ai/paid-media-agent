"""MDA profile: managed backend, threads, and identity; the same assembly and policy."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from paid_media_agent.assembly import AgentComponents, build_agent_components
from paid_media_agent.config import Settings
from paid_media_agent.runtime.profiles import approval_policy_from_settings, fixture_profile
from paid_media_agent.runtime.self_hosted import load_catalog


def build_mda_components(
    settings: Settings, *, project_root: Path, loop: Callable[[Any], Any]
) -> AgentComponents:
    """Build components for the managed runtime. Live catalog only when a token is configured."""
    catalog, provider, live_reads = loop(load_catalog(settings))
    profile = fixture_profile(
        settings,
        project_root=project_root,
        catalog_provider=provider,
        name="mda",
        approval_policy=approval_policy_from_settings(settings),
    )
    if live_reads is not None:
        profile = type(profile)(**{**profile.__dict__, "read_provider": live_reads})
    return build_agent_components(settings=settings, runtime=profile, catalog=catalog)
