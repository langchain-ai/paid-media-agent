"""Opt-in live checks. They skip unless the operator sets the environment explicitly."""

from __future__ import annotations

import os
from pathlib import Path

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
    assert catalog.mutation_entries() == (), "no mutation is admitted before the Slice 6 review"
    for entry in catalog.read_entries():
        assert entry.read_only_hint is True and entry.account_arg is not None


def test_postgres_repositories_roundtrip(project_root: Path) -> None:
    settings = Settings()
    if settings.database_url is None:
        pytest.skip("DATABASE_URL not configured")
    pytest.importorskip("psycopg")
    from paid_media_agent.domain.proposals import ProposalRecord, ProposalState
    from paid_media_agent.persistence.postgres import PostgresRepositories
    from tests.unit.test_proposals_and_security import _changeset

    repos = PostgresRepositories(settings.database_url.get_secret_value())
    repos.setup()
    record = ProposalRecord(
        changeset=_changeset(), state=ProposalState.AWAITING_APPROVAL, routing_id="rt-int"
    )
    repos.proposals.save(record)
    assert repos.proposals.get(record.changeset.proposal_id) == record
    assert repos.dedupe.seen("k") is False and repos.dedupe.seen("k") is True
    repos.close()
