"""Deterministic cross-platform report runs: reads, comparison, and rendering without a model.

The scheduled report is the same pipeline the agent uses, executed by code end to end. The model
is optional and only ever writes the executive summary; every number comes from `compute`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from paid_media_agent.config import AccountRegistry
from paid_media_agent.domain.analysis import PeriodComparison
from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.metrics import MetricWindow
from paid_media_agent.tools.artifacts import ArtifactStore
from paid_media_agent.tools.catalog import AuthorizedToolCatalog, qualified_name
from paid_media_agent.tools.compare_periods import ComparePeriodsArgs, run_compare_periods
from paid_media_agent.tools.reads import ACCOUNT_ALIAS_ARG, ReadDenied, ReadDispatcher
from paid_media_agent.tools.reports import RenderReportArgs, run_render_report

Cadence = Literal["weekly", "monthly"]
PERFORMANCE_TOOL = "get_campaign_performance"


class ReportWindows(BaseModel):
    model_config = ConfigDict(frozen=True)

    cadence: Cadence
    current: MetricWindow
    previous: MetricWindow


def report_windows(cadence: Cadence, *, end: date, timezone: str = "UTC") -> ReportWindows:
    """Complete trailing window ending on `end`, and the equal-length window before it."""
    days = 7 if cadence == "weekly" else 28
    current = MetricWindow(
        start=end - timedelta(days=days - 1), end=end, timezone=timezone, is_complete=True
    )
    previous = MetricWindow(
        start=current.start - timedelta(days=days),
        end=current.start - timedelta(days=1),
        timezone=timezone,
        is_complete=True,
    )
    return ReportWindows(cadence=cadence, current=current, previous=previous)


@dataclass(frozen=True)
class ReportRun:
    cadence: Cadence
    windows: ReportWindows
    read_artifacts: tuple[str, ...]
    unavailable: tuple[str, ...]
    analysis_artifact_id: str
    summary: dict[str, JsonValue]
    report: dict[str, JsonValue] | None
    reconciled: bool


async def run_cadence_report(
    *,
    cadence: Cadence,
    end: date,
    accounts: AccountRegistry,
    catalog: AuthorizedToolCatalog,
    dispatcher: ReadDispatcher,
    artifacts: ArtifactStore,
    aliases: tuple[str, ...] | None = None,
    title: str | None = None,
    executive_summary: str | None = None,
    render: bool = True,
) -> ReportRun:
    """Read every alias's campaign performance, compare the two windows, and render.

    A platform whose read fails stays visible as unavailable and suppresses the cross-platform
    total; healthy platforms still produce sections.
    """
    windows = report_windows(cadence, end=end)
    chosen = tuple(aliases) if aliases else accounts.aliases()
    read_ids: list[str] = []
    unavailable: list[str] = []
    for alias in chosen:
        binding = accounts.resolve(alias)
        if binding is None:
            unavailable.append(f"{alias}: unknown alias")
            continue
        entry = catalog.get(qualified_name(binding.platform, PERFORMANCE_TOOL))
        if entry is None:
            unavailable.append(
                f"{alias}: {binding.platform.value} has no campaign performance read tool"
            )
            continue
        try:
            result = await dispatcher.execute(
                entry.qualified_name,
                {
                    ACCOUNT_ALIAS_ARG: alias,
                    "start_date": windows.previous.start.isoformat(),
                    "end_date": windows.current.end.isoformat(),
                },
            )
        except ReadDenied as exc:
            unavailable.append(f"{alias}: {exc.reason}")
            continue
        except Exception as exc:
            unavailable.append(f"{alias}: {type(exc).__name__}")
            continue
        if result.artifact_kind != "performance_rows":
            unavailable.append(f"{alias}: read returned no performance rows")
            continue
        read_ids.append(result.artifact_id)
    if not read_ids:
        raise RuntimeError("no platform produced performance rows; nothing to compare")
    summary = run_compare_periods(
        artifacts,
        ComparePeriodsArgs(
            artifact_ids=read_ids,
            current_start=windows.current.start,
            current_end=windows.current.end,
            previous_start=windows.previous.start,
            previous_end=windows.previous.end,
            unavailable_sources=unavailable,
        ),
    )
    analysis_id = str(summary["artifact_id"])
    report_payload: dict[str, JsonValue] | None = None
    reconciled = bool(summary["reconciled"])
    if render:
        comparison = PeriodComparison.model_validate(artifacts.read(analysis_id).payload)
        report_payload = run_render_report(
            artifacts,
            RenderReportArgs(
                analysis_artifact_id=analysis_id,
                title=title
                or f"{cadence.capitalize()} paid media report · {windows.current.start.isoformat()} to {windows.current.end.isoformat()}",
                executive_summary=executive_summary or _default_summary(comparison),
                recommendations=[],
            ),
        )
        reconciled = reconciled and bool(report_payload["report"]["reconciled"])
    return ReportRun(
        cadence=cadence,
        windows=windows,
        read_artifacts=tuple(read_ids),
        unavailable=tuple(unavailable),
        analysis_artifact_id=analysis_id,
        summary=summary,
        report=report_payload,
        reconciled=reconciled,
    )


def _default_summary(comparison: PeriodComparison) -> str:
    """A code-written summary that states only what the analysis object contains."""
    parts: list[str] = []
    for platform in comparison.platforms:
        spend = next(d for d in platform.deltas if d.metric == "spend")
        direction = (
            "up" if (spend.relative or 0) > 0 else "down" if (spend.relative or 0) < 0 else "flat"
        )
        pct = f"{abs((spend.relative or 0) * 100):.1f}%"
        parts.append(f"{platform.platform.value} spend {direction} {pct}")
    if comparison.total_suppressed_reason:
        parts.append(f"cross-platform total suppressed ({comparison.total_suppressed_reason})")
    if comparison.unavailable_sources:
        parts.append(f"unavailable: {', '.join(comparison.unavailable_sources)}")
    return "; ".join(parts) + "."
