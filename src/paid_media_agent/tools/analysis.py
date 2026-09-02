"""Model-facing `compare_periods` tool: loads row artifacts and runs deterministic compute."""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from paid_media_agent.domain.analysis import ANALYSIS_SCHEMA_VERSION, PlatformComparison
from paid_media_agent.domain.common import DataQualityFlag, EntityType, Platform
from paid_media_agent.domain.metrics import MetricWindow
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.tools.artifacts import ArtifactError, ArtifactStore
from paid_media_agent.tools.compute import (
    ComputeError,
    compare_periods,
    compare_platform,
    summarize,
)
from paid_media_agent.tools.normalize import NormalizationError, rows_from_payload

COMPARE_PERIODS_TOOL = "compare_periods"


class ComparePeriodsArgs(BaseModel):
    artifact_ids: list[str] = Field(
        description="performance_rows artifact ids returned by platform reads."
    )
    current_start: date
    current_end: date
    previous_start: date
    previous_end: date
    entity_type: EntityType = EntityType.CAMPAIGN
    unavailable_sources: list[str] = Field(
        default_factory=list,
        description="Platforms or accounts whose read failed. They stay visible and suppress totals.",
    )


def run_compare_periods(artifacts: ArtifactStore, args: ComparePeriodsArgs) -> dict[str, Any]:
    if args.current_end < args.current_start or args.previous_end < args.previous_start:
        raise ComputeError("window end precedes start")
    current = MetricWindow(
        start=args.current_start, end=args.current_end, timezone="UTC", is_complete=True
    )
    previous = MetricWindow(
        start=args.previous_start, end=args.previous_end, timezone="UTC", is_complete=True
    )
    if not current.same_length(previous):
        raise ComputeError("comparison windows must have the same day count")
    if not args.artifact_ids:
        raise ComputeError("at least one artifact id is required")
    platforms: list[PlatformComparison] = []
    for artifact_id in args.artifact_ids:
        record = artifacts.read(artifact_id)
        if record.metadata.kind != "performance_rows":
            raise ComputeError(f"{artifact_id} is not a performance_rows artifact")
        rows = rows_from_payload(record.payload)
        if not rows:
            raise ComputeError(f"{artifact_id} contains no rows")
        platform = Platform(record.metadata.platform or rows[0].platform.value)
        account_ref = record.metadata.account_ref or rows[0].account_ref
        provider_totals = record.payload.get("provider_totals") or None
        missing = tuple(str(m) for m in record.payload.get("missing_fields", []))
        tz = rows[0].window.timezone
        platforms.append(
            compare_platform(
                platform=platform,
                account_ref=account_ref,
                rows=rows,
                current_window=MetricWindow(
                    start=current.start, end=current.end, timezone=tz, is_complete=True
                ),
                previous_window=MetricWindow(
                    start=previous.start, end=previous.end, timezone=tz, is_complete=True
                ),
                entity_type=args.entity_type,
                source_artifacts=[artifact_id],
                provider_totals=provider_totals,
                missing_fields=missing,
            )
        )
    comparison = compare_periods(
        platforms=platforms,
        requested_current=current,
        requested_previous=previous,
        unavailable_sources=tuple(args.unavailable_sources),
    )
    flags: set[DataQualityFlag] = set()
    for platform_comparison in platforms:
        flags.update(platform_comparison.quality_flags)
    if comparison.total_suppressed_reason:
        flags.add(DataQualityFlag.SUPPRESSED_TOTAL)
    metadata = artifacts.write_json(
        "analysis",
        comparison.model_dump(mode="json"),
        schema_version=ANALYSIS_SCHEMA_VERSION,
        row_count=sum(p.current.row_count + p.previous.row_count for p in platforms),
        entity_type=args.entity_type.value,
        requested_window=f"{current.start.isoformat()}..{current.end.isoformat()}",
        quality_flags=tuple(sorted(flags)),
        tool_name=COMPARE_PERIODS_TOOL,
    )
    summary = summarize(comparison, metadata.artifact_id)
    return summary.model_dump(mode="json")


def build_compare_periods_tool(artifacts: ArtifactStore) -> BaseTool:
    def _run(**kwargs: Any) -> str:
        try:
            args = ComparePeriodsArgs.model_validate(kwargs)
            return json.dumps(run_compare_periods(artifacts, args))
        except (ComputeError, ArtifactError, NormalizationError, ValueError) as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})

    return StructuredTool(
        name=COMPARE_PERIODS_TOOL,
        description=(
            "Deterministically compare a current window with a previous window of equal length across "
            "performance_rows artifacts. Returns a compact summary with an analysis artifact id. "
            "Missing metrics stay missing; a cross-platform total appears only when sources are compatible."
        ),
        args_schema=ComparePeriodsArgs,
        func=_run,
    )
