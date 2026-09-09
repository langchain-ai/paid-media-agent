"""Opt-in live checks. They skip unless the operator sets the environment explicitly."""

from __future__ import annotations

import os

import pytest

from paid_media_agent.config import Settings

pytestmark = pytest.mark.skipif(
    os.environ.get("PAID_MEDIA_LIVE_TESTS") != "1",
    reason="set PAID_MEDIA_LIVE_TESTS=1 to run live read-only checks",
)


async def test_pipeboard_catalog_loads_and_denies_mutations() -> None:
    settings = Settings()
    if settings.pipeboard_api_token is None:
        pytest.skip("PIPEBOARD_API_TOKEN not configured")
    from paid_media_agent.tools.pipeboard import PipeboardCatalogLoader

    loader = PipeboardCatalogLoader(settings=settings)
    catalog = await loader.refresh()
    assert catalog.source == "pipeboard"
    assert catalog.mutation_entries() == (), (
        "no mutation is admitted before the live-write release review"
    )
    for entry in catalog.read_entries():
        assert entry.read_only_hint is True and entry.account_arg is not None
