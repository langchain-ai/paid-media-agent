"""Reads below campaign grain: fixture ad groups reconcile to campaigns and rows keep their grain."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from paid_media_agent.domain.common import EntityType
from paid_media_agent.runtime.profiles import fixture_profile
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.fixtures import (
    FixtureReadProvider,
    FixtureState,
    build_fixture_catalog,
)
from paid_media_agent.tools.normalize import entity_keys, rows_from_payload
from paid_media_agent.tools.reads import ReadDispatcher, entity_type_for


def test_entity_type_comes_from_the_payload_then_the_tool_name() -> None:
    assert entity_type_for("get_campaign_performance") is EntityType.CAMPAIGN
    assert entity_type_for("get_ad_group_performance") is EntityType.AD_GROUP
    assert entity_type_for("get_adset_insights") is EntityType.AD_GROUP
    assert entity_type_for("get_creative_performance") is EntityType.CREATIVE
    assert entity_type_for("get_keyword_performance") is EntityType.KEYWORD
    assert entity_type_for("get_campaign_performance", "ad_group") is EntityType.AD_GROUP
    assert entity_type_for("get_campaign_performance", "not-a-grain") is EntityType.CAMPAIGN


def test_grain_specific_keys_come_first() -> None:
    ids, names = entity_keys(EntityType.AD_GROUP)
    assert ids[:3] == ("ad_group_id", "adset_id", "line_item_id") and ids[-1] == "id"
    assert names[0] == "ad_group_name"
    assert entity_keys(EntityType.CAMPAIGN)[0][0] == "campaign_id"


@pytest.mark.parametrize("platform", ["google_ads", "meta_ads", "reddit_ads"])
async def test_fixture_ad_groups_reconcile_to_their_campaign(tmp_path, platform: str) -> None:
    from paid_media_agent.config import Settings

    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    provider = StaticCatalogProvider(build_fixture_catalog())
    state = FixtureState()
    profile = fixture_profile(
        settings,
        project_root=Path(__file__).resolve().parents[2],
        catalog_provider=provider,
        fixture_state=state,
        workspace_root=tmp_path / "workspace",
    )
    store = ArtifactStore(tmp_path / "workspace")
    dispatcher = ReadDispatcher(
        catalog_provider=provider,
        provider=FixtureReadProvider(state),
        accounts=profile.accounts,
        artifacts=store,
    )
    alias = next(b.alias for b in profile.accounts.bindings if b.platform.value == platform)
    window = {"account_alias": alias, "start_date": "2026-08-10", "end_date": "2026-08-16"}
    campaigns = await dispatcher.execute(f"{platform}__get_campaign_performance", window)
    ad_groups = await dispatcher.execute(f"{platform}__get_ad_group_performance", window)

    assert ad_groups.artifact_kind == "performance_rows"
    campaign_rows = rows_from_payload(store.read(campaigns.artifact_id).payload)
    group_rows = rows_from_payload(store.read(ad_groups.artifact_id).payload)
    assert {r.entity_type for r in group_rows} == {EntityType.AD_GROUP}
    assert len({r.entity_ref for r in group_rows}) == 2 * len({r.entity_ref for r in campaign_rows})
    assert sum(r.spend for r in group_rows) == sum(r.spend for r in campaign_rows)
    assert sum(r.conversions or Decimal(0) for r in group_rows) == sum(
        r.conversions or Decimal(0) for r in campaign_rows
    )
    assert group_rows[0].entity_name.endswith("ad group A")
