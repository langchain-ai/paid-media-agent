"""summarize_window owns the arithmetic for pacing, anomalies, and top-N inside one window."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from paid_media_agent.domain.common import Platform
from paid_media_agent.domain.metrics import EntityType, MetricWindow, PerformanceRow
from paid_media_agent.tools.analysis import ComparePeriodsArgs, run_compare_periods
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.compute import ComputeError
from paid_media_agent.tools.normalize import ROWS_SCHEMA_VERSION, rows_to_payload
from paid_media_agent.tools.summary import SummarizeWindowArgs, run_summarize_window


def _row(day: int, entity: str, spend: str, conversions: str) -> PerformanceRow:
    when = date(2026, 8, day)
    return PerformanceRow(
        platform=Platform.GOOGLE_ADS,
        account_ref="demo-google",
        entity_type=EntityType.CAMPAIGN,
        entity_ref=entity,
        entity_name=f"Campaign {entity}",
        window=MetricWindow(start=when, end=when, timezone="UTC", is_complete=True),
        currency="USD",
        spend=Decimal(spend),
        impressions=1000,
        clicks=50,
        conversions=Decimal(conversions),
    )


def test_summary_computes_pacing_top_spenders_and_flagged_days(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)
    rows = [_row(d, "g-1", "100", "2") for d in range(1, 8)] + [
        _row(d, "g-2", "20" if d != 5 else "80", "1") for d in range(1, 8)
    ]
    perf = store.write_json(
        "performance_rows",
        rows_to_payload(rows),
        schema_version=ROWS_SCHEMA_VERSION,
        platform="google_ads",
        account_ref="demo-google",
    )
    budgets = store.write_json(
        "provider_result",
        {
            "result": {
                "campaigns": [{"id": "g-1", "daily_budget": 90}, {"id": "g-2", "daily_budget": 50}]
            }
        },
        schema_version="provider-result/1",
    )

    out = run_summarize_window(
        store,
        SummarizeWindowArgs(
            artifact_ids=[perf.artifact_id],
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 7),
            budgets_artifact_ids=[budgets.artifact_id],
        ),
    )

    google = out["platforms"]["google_ads"]
    assert google["totals"]["spend"] == "900.00"
    top, second = google["entities"]
    assert (top["entity_ref"], top["pacing"], top["daily_budget"]) == ("g-1", "1.1111", "90.00")
    assert second["pacing"] == "0.5714"  # 200 / 7 days = 28.57 against a 50 budget
    assert google["over_budget"] == ["g-1"]
    assert google["flagged_days"] == ["2026-08-05"]  # +50% day; the -33% return is below the flag
    assert store.read(out["artifact_id"]).metadata.tool_name == "summarize_window"


def test_compare_periods_refuses_an_empty_window_instead_of_reporting_zero(tmp_path: Path) -> None:
    """September had no rows; the comparison rendered 0.00 spend and -100%, which reads as a
    collapse rather than missing data."""
    store = ArtifactStore(tmp_path)
    rows = [_row(d, "g-1", "100", "2") for d in range(1, 8)]
    perf = store.write_json(
        "performance_rows",
        rows_to_payload(rows),
        schema_version=ROWS_SCHEMA_VERSION,
        platform="google_ads",
        account_ref="demo-google",
    )
    args = ComparePeriodsArgs(
        artifact_ids=[perf.artifact_id],
        current_start=date(2026, 9, 1),
        current_end=date(2026, 9, 7),
        previous_start=date(2026, 8, 1),
        previous_end=date(2026, 8, 7),
    )
    try:
        run_compare_periods(store, args)
    except ComputeError as exc:
        assert "no rows in the current window" in str(exc)
        assert "data through 2026-08-07" in str(exc)
    else:
        raise AssertionError("expected ComputeError")


def test_compare_periods_refuses_a_window_the_read_did_not_cover(tmp_path: Path) -> None:
    """Rows for Aug 21 to 28 compared as Aug 15 to 21 versus Aug 22 to 28 made one day look like a
    week and the following week look like a six-fold surge."""
    store = ArtifactStore(tmp_path)
    rows = [_row(d, "g-1", "100", "2") for d in range(21, 29)]
    perf = store.write_json(
        "performance_rows",
        rows_to_payload(rows),
        schema_version=ROWS_SCHEMA_VERSION,
        platform="google_ads",
        account_ref="demo-google",
    )
    args = ComparePeriodsArgs(
        artifact_ids=[perf.artifact_id],
        current_start=date(2026, 8, 22),
        current_end=date(2026, 8, 28),
        previous_start=date(2026, 8, 15),
        previous_end=date(2026, 8, 21),
    )
    try:
        run_compare_periods(store, args)
    except ComputeError as exc:
        assert "previous window starts 2026-08-15 but the read begins 2026-08-21" in str(exc)
    else:
        raise AssertionError("expected ComputeError")
