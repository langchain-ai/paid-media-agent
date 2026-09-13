from __future__ import annotations

from datetime import date
from pathlib import Path

from paid_media_agent.config import Settings
from paid_media_agent.reports.cadence import report_windows, run_cadence_report
from paid_media_agent.runtime.local import build_local_runtime
from paid_media_agent.testing.demo_script import build_demo_model


def test_report_windows_are_complete_and_equal_length() -> None:
    weekly = report_windows("weekly", end=date(2026, 8, 28))
    assert (weekly.current.start, weekly.current.end) == (date(2026, 8, 22), date(2026, 8, 28))
    assert (weekly.previous.start, weekly.previous.end) == (date(2026, 8, 15), date(2026, 8, 21))
    monthly = report_windows("monthly", end=date(2026, 8, 28))
    assert monthly.current.day_count == 28 and monthly.previous.end == date(2026, 7, 31)


async def test_weekly_report_runs_deterministically_on_fixtures(
    settings: Settings, project_root: Path
) -> None:
    runtime = build_local_runtime(settings, project_root=project_root, model=build_demo_model())
    run = await run_cadence_report(
        cadence="weekly",
        end=date(2026, 8, 28),
        accounts=runtime.profile.accounts,
        catalog=runtime.catalog,
        dispatcher=runtime.components.read_dispatcher,
        artifacts=runtime.profile.artifacts,
    )
    assert len(run.read_artifacts) == 3 and run.unavailable == ()
    assert run.reconciled and run.report is not None
    assert {p["platform"] for p in run.summary["platforms"]} == {
        "google_ads",
        "meta_ads",
        "reddit_ads",
    }
    assert run.summary["total_suppressed_reason"], (
        "reddit is incomplete in the fixture, so the total stays suppressed"
    )
    assert any(path["path"].endswith(".html") for path in run.report["files"])


async def test_unknown_alias_stays_visible_as_unavailable(
    settings: Settings, project_root: Path
) -> None:
    runtime = build_local_runtime(settings, project_root=project_root, model=build_demo_model())
    run = await run_cadence_report(
        cadence="weekly",
        end=date(2026, 8, 28),
        accounts=runtime.profile.accounts,
        catalog=runtime.catalog,
        dispatcher=runtime.components.read_dispatcher,
        artifacts=runtime.profile.artifacts,
        aliases=("demo-google", "ghost"),
        render=False,
    )
    assert run.read_artifacts and run.unavailable == ("ghost: unknown alias",)
    assert run.summary["unavailable_sources"] == ["ghost: unknown alias"]


async def test_report_reconciles_accounts_on_the_same_platform(
    settings: Settings, project_root: Path
) -> None:
    from paid_media_agent.domain.analysis import PeriodComparison
    from paid_media_agent.reports.render import build_report_payload, reconcile_report
    from paid_media_agent.runtime.local import build_local_runtime
    from paid_media_agent.testing.scripted_model import ScriptedChatModel

    runtime = build_local_runtime(
        settings, project_root=project_root, model=ScriptedChatModel(steps=[])
    )
    run = await run_cadence_report(
        cadence="weekly",
        end=date(2026, 8, 28),
        accounts=runtime.profile.accounts,
        catalog=runtime.catalog,
        dispatcher=runtime.components.read_dispatcher,
        artifacts=runtime.profile.artifacts,
        aliases=("demo-google",),
        render=False,
    )
    comparison = PeriodComparison.model_validate(
        runtime.profile.artifacts.read(run.analysis_artifact_id).payload
    )
    first = comparison.platforms[0]
    second = first.model_copy(update={"account_ref": "second-account", "current": first.previous})
    comparison = comparison.model_copy(update={"platforms": (first, second)})
    payload = build_report_payload(
        comparison,
        analysis_artifact_id=run.analysis_artifact_id,
        title="Accounts",
        executive_summary="",
    )
    assert reconcile_report(payload, comparison) == ()
    missing = payload.model_copy(update={"platform_sections": payload.platform_sections[:1]})
    assert any("second-account" in issue for issue in reconcile_report(missing, comparison))
