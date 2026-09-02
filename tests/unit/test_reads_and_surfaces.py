from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.analysis import PeriodComparison
from paid_media_agent.domain.presentation import ProposalView, ReceiptView
from paid_media_agent.domain.proposals import ProposalRecord, ProposalState, WriteReceipt
from paid_media_agent.reports.bridge import ArtifactBridge, BridgeError
from paid_media_agent.reports.render import ReportRenderer, build_report_payload, reconcile_report
from paid_media_agent.surfaces.api.app import resolve_caller
from paid_media_agent.surfaces.slack.blocks import (
    ACTION_APPROVE,
    render_proposal,
    render_receipt,
    render_report,
)
from paid_media_agent.tools.analysis import ComparePeriodsArgs, run_compare_periods
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import StaticCatalogProvider
from paid_media_agent.tools.fixtures import FixtureReadProvider, FixtureState, build_fixture_catalog
from paid_media_agent.tools.reads import ReadDenied, ReadDispatcher, model_facing_schema
from paid_media_agent.tools.reports import RenderReportArgs, run_render_report
from tests.unit.test_proposals_and_security import _changeset


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
    dispatcher: ReadDispatcher, tmp_path: Path
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
    assert "Cross-platform total suppressed" in html
    comparison = PeriodComparison.model_validate(artifacts.read(summary["artifact_id"]).payload)
    payload = build_report_payload(
        comparison, analysis_artifact_id=summary["artifact_id"], title="t", executive_summary="s"
    )
    assert reconcile_report(payload, comparison) == ()
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
    slack = render_report(
        json.loads(json.dumps(rendered["report"]))
        and __import__(
            "paid_media_agent.domain.presentation", fromlist=["ReportSummary"]
        ).ReportSummary.model_validate(rendered["report"])
    )
    assert slack.text and all(
        len(b.get("text", {}).get("text", "")) <= 3000
        for b in slack.blocks
        if b["type"] == "section"
    )


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


def test_bridge_rejects_outside_paths_and_types(tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    bridge = ArtifactBridge(out)
    (out / "ok.html").write_text("<p>x</p>")
    assert bridge.validate(out / "ok.html").media_type == "text/html"
    (tmp_path / "secret.html").write_text("x")
    with pytest.raises(BridgeError):
        bridge.validate(tmp_path / "secret.html")
    with pytest.raises(BridgeError):
        bridge.validate(out / ".." / "secret.html")
    (out / "bin.exe").write_bytes(b"x")
    with pytest.raises(BridgeError):
        bridge.validate(out / "bin.exe")


def test_slack_blocks_escape_and_use_opaque_values() -> None:
    record = ProposalRecord(
        changeset=_changeset(reason="<script>&"),
        state=ProposalState.AWAITING_APPROVAL,
        routing_id="route-abc",
    )
    view = ProposalView.from_record(record)
    message = render_proposal(view, can_act=True)
    assert message.text
    dumped = json.dumps(list(message.blocks))
    assert "<script>" not in dumped and "&lt;script&gt;" in dumped
    actions = next(b for b in message.blocks if b["type"] == "actions")
    approve = next(e for e in actions["elements"] if e["action_id"] == ACTION_APPROVE)
    assert approve["value"] == "route-abc" and "daily_budget" not in approve["value"]
    receipt = WriteReceipt(
        proposal_id=view.proposal_id,
        revision=1,
        status="unknown",
        mutation_attempted=True,
        provider_operation_ref=None,
        verified_state=(),
        checked_at=datetime.now(UTC),
        catalog_revision="r",
        reason="timeout",
    )
    unknown = render_receipt(ReceiptView.from_receipt(receipt))
    assert "Do not retry" in json.dumps(list(unknown.blocks))


def test_api_bearer_lookup_is_exact() -> None:
    tokens = {"tok-one": "alice"}
    assert resolve_caller(tokens, "Bearer tok-one") == "alice"
    assert resolve_caller(tokens, "Bearer tok-on") is None
    assert resolve_caller(tokens, "tok-one") is None
    assert resolve_caller({}, "Bearer tok-one") is None
