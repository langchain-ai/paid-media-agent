from __future__ import annotations

import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.analysis import PeriodComparison
from paid_media_agent.reports.bridge import ArtifactBridge, BridgeError
from paid_media_agent.reports.render import ReportRenderer, build_report_payload, reconcile_report
from paid_media_agent.surfaces.api.app import resolve_caller
from paid_media_agent.surfaces.slack.blocks import (
    ACTION_APPROVE,
    approval_message,
)
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.compare_periods import ComparePeriodsArgs, run_compare_periods
from paid_media_agent.tools.fixtures import FixtureReadProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.reads import ReadDenied, ReadDispatcher, model_facing_schema
from paid_media_agent.tools.reports import RenderReportArgs, run_render_report


@pytest.fixture
def dispatcher(tmp_path: Path, project_root: Path) -> ReadDispatcher:
    return ReadDispatcher(
        catalog_provider=StaticCatalogProvider(build_fixture_catalog()),
        accounts=AccountRegistry.from_toml(project_root / "config" / "accounts.example.toml"),
        provider=FixtureReadProvider(FixtureState()),
        artifacts=ArtifactStore(tmp_path / "ws"),
    )


def test_model_facing_schema_hides_provider_account_argument() -> None:
    entry = build_fixture_catalog().get("google_ads__get_campaign_performance")
    assert entry is not None
    schema = model_facing_schema(entry, ["demo-google"])
    assert "customer_id" not in schema["properties"]
    assert schema["required"][0] == "account_alias"
    assert schema["properties"]["account_alias"]["enum"] == ["demo-google"]


async def test_dispatcher_rejects_raw_ids_bad_schema_and_wrong_platform(
    dispatcher: ReadDispatcher,
) -> None:
    good = {"account_alias": "demo-google", "start_date": "2026-08-01", "end_date": "2026-08-28"}
    result = await dispatcher.execute("google_ads__get_campaign_performance", good)
    assert result.row_count == 82 and result.artifact_kind == "performance_rows"
    with pytest.raises(ReadDenied, match="raw_account_id_rejected"):
        await dispatcher.execute(
            "google_ads__get_campaign_performance", {**good, "customer_id": "fixture-google-0001"}
        )
    with pytest.raises(ReadDenied, match="raw_account_id_rejected"):
        await dispatcher.execute(
            "google_ads__get_campaign",
            {"account_alias": "demo-google", "campaign_id": "fixture-meta-0001"},
        )
    with pytest.raises(ReadDenied, match="platform_scope"):
        await dispatcher.execute(
            "google_ads__get_campaign_performance", {**good, "account_alias": "demo-meta"}
        )
    with pytest.raises(ReadDenied, match="schema_validation_failed"):
        await dispatcher.execute(
            "google_ads__get_campaign_performance",
            {"account_alias": "demo-google", "start_date": "2026-08-01"},
        )
    with pytest.raises(ReadDenied, match="schema_validation_failed"):
        await dispatcher.execute("google_ads__get_campaign_performance", {**good, "extra": 1})
    with pytest.raises(ReadDenied, match="unknown_tool"):
        await dispatcher.execute("google_ads__made_up_tool", good)
    with pytest.raises(ReadDenied, match="not_a_read_tool"):
        await dispatcher.execute(
            "google_ads__update_campaign_budget",
            {"account_alias": "demo-google", "campaign_id": "g-101", "daily_budget": 1},
        )
    with pytest.raises(ReadDenied, match="stale_selection"):
        await dispatcher.execute(
            "google_ads__get_campaign_performance", good, selection_schema_hash="deadbeef"
        )
    assert all("fixture-google-0001" not in json.dumps(item) for item in dispatcher.audit)


async def test_report_reconciles_and_shows_missing_platforms(
    dispatcher: ReadDispatcher, tmp_path: Path, project_root: Path
) -> None:
    artifacts = ArtifactStore(tmp_path / "ws")
    ids = []
    for alias, platform in (("demo-google", "google_ads"), ("demo-reddit", "reddit_ads")):
        result = await dispatcher.execute(
            f"{platform}__get_campaign_performance",
            {"account_alias": alias, "start_date": "2026-08-01", "end_date": "2026-08-28"},
        )
        ids.append(result.artifact_id)
    summary = run_compare_periods(
        artifacts,
        ComparePeriodsArgs(
            artifact_ids=ids,
            current_start=date(2026, 8, 15),
            current_end=date(2026, 8, 28),
            previous_start=date(2026, 8, 1),
            previous_end=date(2026, 8, 14),
            unavailable_sources=["meta_ads"],
        ),
    )
    assert summary["cross_platform_total"] is None and "meta_ads" in summary["unavailable_sources"]
    reddit = next(p for p in summary["platforms"] if p["platform"] == "reddit_ads")
    assert (
        reddit["roas_current"] == "unavailable" and "conversion_value" in reddit["missing_fields"]
    )
    rendered = run_render_report(
        artifacts,
        RenderReportArgs(
            analysis_artifact_id=summary["artifact_id"],
            title="Weekly",
            executive_summary="Spend held; Reddit value unavailable.",
        ),
    )
    html = (tmp_path / "ws" / "out" / rendered["files"][0]["path"]).read_text()
    assert "meta_ads" in html and "unavailable" in html and "conversion_value" in html
    assert "No combined total" in html
    assert "Aug 15-28, 2026" in html and "Aug 1-14, 2026" in html
    assert 'class="brand-logo"' not in html
    assert "Cost per conversion" in html and "Return on ad spend" in html
    assert 'class="chart-dots"' in html
    assert 'class="change change-increase">+' in html
    assert 'class="change change-decrease">-' in html
    comparison = PeriodComparison.model_validate(artifacts.read(summary["artifact_id"]).payload)
    payload = build_report_payload(
        comparison, analysis_artifact_id=summary["artifact_id"], title="t", executive_summary="s"
    )
    assert reconcile_report(payload, comparison) == ()

    templates = tmp_path / "company-templates"
    shutil.copytree(project_root / "src/paid_media_agent/reports/templates", templates)
    theme = templates / "tokens.j2"
    theme.write_text(
        theme.read_text()
        .replace("Paid Media Agent", "Example company")
        .replace("#006ddd", "#7c3a70")
        .replace(
            "Inter, -apple-system, BlinkMacSystemFont, Segoe UI, Helvetica, Arial, sans-serif",
            "Georgia, serif",
        )
    )
    branded = ReportRenderer(tmp_path / "company-out", templates_dir=templates).render_html(payload)
    assert "--current: #7c3a70" in branded and 'fill="#7c3a70"' in branded
    assert "#006ddd" not in branded
    assert "--font-family: Georgia, serif" in branded and "font: 8pt Georgia, serif" in branded
    assert 'content: "Example company"' in branded
    assert "font: var(--heading-weight) 19px" in branded
    assert all(
        row.current in branded for section in payload.platform_sections for row in section.rows
    )

    broken = payload.model_copy(update={"platform_sections": payload.platform_sections[:1]})
    assert any("missing" in p for p in reconcile_report(broken, comparison))
    tampered_row = payload.platform_sections[0].rows[0].model_copy(update={"raw_current": "1"})
    tampered_section = payload.platform_sections[0].model_copy(
        update={"rows": (tampered_row, *payload.platform_sections[0].rows[1:])}
    )
    tampered = payload.model_copy(
        update={"platform_sections": (tampered_section, *payload.platform_sections[1:])}
    )
    assert reconcile_report(tampered, comparison)


def test_renderer_escapes_model_text(tmp_path: Path) -> None:
    renderer = ReportRenderer(tmp_path / "out")
    from paid_media_agent.domain.reports import ReportPayload, ReportProvenance, ReportScope

    payload = ReportPayload(
        report_id="rpt_test",
        title="<script>alert(1)</script>",
        scope=ReportScope(
            accounts=(),
            platforms=(),
            current_window="w",
            previous_window="p",
            currency=None,
            source_coverage="none",
        ),
        executive_summary="<b>bold</b>",
        scorecard=(),
        total_suppressed_reason="no data",
        platform_sections=(),
        recommendations=(),
        data_quality=("x",),
        unavailable_sources=(),
        provenance=ReportProvenance(
            analysis_artifact_id="art_0000000000000000",
            source_artifacts=(),
            analysis_version="v",
            analysis_schema_version="s",
            generated_at=datetime(2026, 9, 1, tzinfo=UTC),
        ),
    )
    html = renderer.render_html(payload)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_report_dates_keep_month_and_year_boundaries() -> None:
    from paid_media_agent.reports.render import _format_window

    assert _format_window("2026-08-29..2026-09-04") == "Aug 29-Sep 4, 2026"
    assert _format_window("2025-12-29..2026-01-04") == "Dec 29, 2025-Jan 4, 2026"
    assert _format_window("unavailable") == "unavailable"


def test_report_chart_scales_preserve_currency_zero_and_missing() -> None:
    from paid_media_agent.domain.common import Platform
    from paid_media_agent.domain.reports import PlatformSection, ScorecardRow
    from paid_media_agent.reports.render import comparison_charts

    def section(
        account: str, currency: str, current: str | None, previous: str, metric: str = "spend"
    ) -> PlatformSection:
        return PlatformSection(
            platform=Platform.GOOGLE_ADS,
            account_ref=account,
            currency=currency,
            rows=(
                ScorecardRow(
                    metric=metric,
                    definition="Spend",
                    current=current or "unavailable",
                    previous=previous,
                    change="unavailable",
                    raw_current=current,
                    raw_previous=previous,
                ),
            ),
            drivers=(),
            missing_fields=(),
            quality_flags=(),
        )

    charts = comparison_charts(
        (
            section("first", "USD", "100", "50"),
            section("missing", "USD", None, "0"),
            section("zero", "EUR", "0", "0"),
        )
    )
    usd = next(c for c in charts if "USD" in c.title)
    eur = next(c for c in charts if "EUR" in c.title)
    assert [r.account for r in usd.rows] == ["first", "missing"]
    assert usd.maximum == "100" and eur.maximum == "0"
    assert usd.rows[0].current_width == "100.0000"
    assert usd.rows[0].previous_width == "50.0000"
    assert usd.rows[1].current_width is None
    assert usd.rows[1].current == "unavailable"
    assert usd.rows[1].previous_width == "0.0000"
    assert eur.rows[0].current_width == eur.rows[0].previous_width == "0.0000"

    invalid = section("invalid", "USD", "NaN", "-1")
    assert comparison_charts((invalid,)) == ()

    efficiency = comparison_charts(
        (
            section("usd", "USD", "20", "40", "cpa"),
            section("eur", "EUR", "100", "50", "cpa"),
            section("return", "USD", None, "2", "roas"),
        )
    )
    assert [c.metric for c in efficiency] == ["cpa", "cpa", "roas"]
    usd_cpa = next(c for c in efficiency if "USD" in c.title)
    assert usd_cpa.rows[0].current_width == "50.0000"
    assert usd_cpa.rows[0].previous_width == "100.0000"
    assert efficiency[-1].rows[0].current_width is None
    assert efficiency[-1].rows[0].previous_width == "100.0000"


def test_bridge_rejects_outside_paths_and_types(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    bridge = ArtifactBridge(out)
    (out / "ok.html").write_text("<p>x</p>")
    assert bridge.validate(out / "ok.html").media_type == "text/html"
    (out / "alias.html").symlink_to(out / "ok.html")
    with pytest.raises(BridgeError, match="symlinked"):
        bridge.validate(out / "alias.html")
    (tmp_path / "secret.html").write_text("x")
    with pytest.raises(BridgeError):
        bridge.validate(tmp_path / "secret.html")
    with pytest.raises(BridgeError):
        bridge.validate(out / ".." / "secret.html")
    (out / "bin.exe").write_bytes(b"x")
    with pytest.raises(BridgeError):
        bridge.validate(out / "bin.exe")


def test_approval_actions_use_only_opaque_routing_values() -> None:
    message = approval_message("Review the proposed change.", "route-abc")
    assert message.text == "Review the proposed change."
    actions = message.blocks[0]
    assert actions["type"] == "actions"
    approve = next(e for e in actions["elements"] if e["action_id"] == ACTION_APPROVE)
    assert approve["value"] == "route-abc"
    assert {element["value"] for element in actions["elements"]} == {"route-abc"}


def test_api_bearer_lookup_is_exact() -> None:
    tokens = {"tok-one": "alice"}
    assert resolve_caller(tokens, "Bearer tok-one") == "alice"
    assert resolve_caller(tokens, "Bearer tok-on") is None
    assert resolve_caller(tokens, "tok-one") is None
    assert resolve_caller({}, "Bearer tok-one") is None
