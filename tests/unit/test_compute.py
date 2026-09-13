from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from paid_media_agent.domain.common import DataQualityFlag, EntityType, Platform
from paid_media_agent.domain.metrics import MetricWindow, PerformanceRow
from paid_media_agent.tools.compute import (
    aggregate,
    compare_periods,
    compare_platform,
    deltas,
    summarize,
)
from paid_media_agent.tools.fixtures import load_fixture_dataset
from paid_media_agent.tools.normalize import normalize_rows

CURRENT = MetricWindow(
    start=date(2026, 8, 15), end=date(2026, 8, 28), timezone="America/New_York", is_complete=True
)
PREVIOUS = MetricWindow(
    start=date(2026, 8, 1), end=date(2026, 8, 14), timezone="America/New_York", is_complete=True
)


def _row(
    day: date,
    spend: str,
    clicks: int | None,
    impressions: int | None,
    conv: str | None,
    value: str | None,
    ref: str = "c1",
) -> PerformanceRow:
    return PerformanceRow(
        platform=Platform.GOOGLE_ADS,
        account_ref="a",
        entity_type=EntityType.CAMPAIGN,
        entity_ref=ref,
        entity_name=ref,
        window=MetricWindow(start=day, end=day, timezone="UTC", is_complete=True),
        currency="USD",
        spend=Decimal(spend),
        clicks=clicks,
        impressions=impressions,
        conversions=Decimal(conv) if conv is not None else None,
        conversion_value=Decimal(value) if value is not None else None,
    )


def test_missing_metric_stays_missing_and_zero_denominators_are_unavailable() -> None:
    rows = [
        _row(date(2026, 8, 1), "10.00", 0, 100, None, None),
        _row(date(2026, 8, 2), "5.50", 0, 50, None, None),
    ]
    agg = aggregate(rows)
    assert agg.spend == Decimal("15.500000")
    assert agg.conversions is None and agg.conversion_value is None
    assert (
        agg.cpa is None and agg.roas is None and agg.cpc is None
    )  # zero clicks -> unavailable, not infinity
    assert agg.ctr == Decimal("0")
    assert agg.cpm == Decimal("103.333333")


def test_deltas_handle_missing_and_zero_previous() -> None:
    cur = aggregate([_row(date(2026, 8, 2), "10", 10, 100, "2", "40")])
    prev = aggregate([_row(date(2026, 8, 1), "0", 0, 100, None, None)])
    by = {d.metric: d for d in deltas(cur, prev)}
    assert by["spend"].absolute == Decimal("10") and by["spend"].relative is None  # previous zero
    assert (
        by["conversions"].absolute is None and by["conversions"].relative is None
    )  # previous missing


def test_platform_comparison_reconciles_to_fixture_oracle(project_root: Path) -> None:
    data = load_fixture_dataset(Platform.GOOGLE_ADS)
    native = [
        {
            "date": r["date"],
            "campaign_id": r["campaign_id"],
            "cost_micros": int(Decimal(str(r["spend"])) * 1_000_000),
            "impressions": r["impressions"],
            "clicks": r["clicks"],
            "conversions": r["conversions"],
            "conversions_value": r["value"],
        }
        for r in data["daily"]
    ]
    rows, missing = normalize_rows(
        platform=Platform.GOOGLE_ADS,
        account_ref="demo-google",
        currency="USD",
        timezone="America/New_York",
        rows=native,
        entity_type=EntityType.CAMPAIGN,
        entity_names={c["id"]: c["name"] for c in data["campaigns"]},
        data_complete_through=date.fromisoformat(data["data_complete_through"]),
    )
    assert missing == ()
    result = compare_platform(
        platform=Platform.GOOGLE_ADS,
        account_ref="demo-google",
        rows=rows,
        current_window=CURRENT,
        previous_window=PREVIOUS,
        entity_type=EntityType.CAMPAIGN,
        source_artifacts=["art_x"],
        provider_totals={
            "spend": str(sum(Decimal(str(r["spend"])) for r in data["daily"])),
            "row_count": len(data["daily"]),
        },
    )
    # Independent oracle straight from the JSON fixture.
    raw_current = [r for r in data["daily"] if "2026-08-15" <= r["date"] <= "2026-08-28"]
    oracle_spend = sum(Decimal(str(r["spend"])) for r in raw_current)
    oracle_conv = sum(Decimal(str(r["conversions"])) for r in raw_current)
    assert result.current.spend == oracle_spend.quantize(Decimal("0.000001"))
    assert result.current.conversions == oracle_conv.quantize(Decimal("0.000001"))
    assert result.current.cpa == (oracle_spend / oracle_conv).quantize(Decimal("0.000001"))
    assert all(check.passed for check in result.reconciliation), result.reconciliation
    g103 = next(e for e in result.entities if e.entity_ref == "g-103")
    assert DataQualityFlag.INCOMPLETE_WINDOW in g103.quality_flags
    assert not result.current_window.is_complete and result.previous_window.is_complete
    assert sum(e.current.spend for e in result.entities) == result.current.spend


def test_cross_platform_total_requires_compatible_complete_sources() -> None:
    complete_rows = [_row(d, "1.00", 1, 10, "1", "2") for d in CURRENT.days() + PREVIOUS.days()]
    complete = compare_platform(
        platform=Platform.GOOGLE_ADS,
        account_ref="a",
        rows=complete_rows,
        current_window=CURRENT,
        previous_window=PREVIOUS,
        entity_type=EntityType.CAMPAIGN,
        source_artifacts=[],
    )
    total = compare_periods(
        platforms=[complete, complete], requested_current=CURRENT, requested_previous=PREVIOUS
    )
    assert total.cross_platform_total is not None and total.cross_platform_total.spend == Decimal(
        "28.000000"
    )
    partial_rows = [_row(d, "1.00", 1, 10, None, None) for d in CURRENT.days() + PREVIOUS.days()]
    partial = compare_platform(
        platform=Platform.META_ADS,
        account_ref="b",
        rows=partial_rows,
        current_window=CURRENT,
        previous_window=PREVIOUS,
        entity_type=EntityType.CAMPAIGN,
        source_artifacts=[],
        missing_fields=["conversions"],
    )
    suppressed = compare_periods(
        platforms=[complete, partial], requested_current=CURRENT, requested_previous=PREVIOUS
    )
    assert suppressed.cross_platform_total is None and "missing" in (
        suppressed.total_suppressed_reason or ""
    )
    unavailable = compare_periods(
        platforms=[complete],
        requested_current=CURRENT,
        requested_previous=PREVIOUS,
        unavailable_sources=["reddit_ads"],
    )
    assert unavailable.cross_platform_total is None
    summary = summarize(unavailable, "art_summary")
    assert summary.cross_platform_total is None and summary.unavailable_sources == ("reddit_ads",)
    assert json.loads(summary.model_dump_json())["platforms"][0]["spend_current"] == "14.00 USD"


def test_normalization_preserves_zero_clicks() -> None:
    rows, _ = normalize_rows(
        platform=Platform.GOOGLE_ADS,
        account_ref="example",
        currency="USD",
        timezone="UTC",
        rows=[
            {
                "date": "2026-08-01",
                "campaign_id": "c1",
                "spend": "10",
                "impressions": 100,
                "clicks": 0,
                "link_clicks": 5,
            }
        ],
        entity_type=EntityType.CAMPAIGN,
        data_complete_through=None,
    )
    assert rows[0].clicks == 0
    assert aggregate(rows).ctr == Decimal(0)
