"""Model-facing `summarize_window` tool: one window, per-entity totals, daily series, and pacing.

`compare_periods` answers "what changed between two windows". This answers "what happened in one
window": which entities carried the spend, how each day moved, and whether spend ran ahead of the
configured daily budget. All arithmetic is here so the model never derives a figure in prose.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from paid_media_agent.domain.common import JsonValue
from paid_media_agent.domain.metrics import PerformanceRow
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.tools.artifacts import ArtifactError, ArtifactStore
from paid_media_agent.tools.compute import ComputeError, aggregate
from paid_media_agent.tools.normalize import NormalizationError, rows_from_payload

SUMMARIZE_WINDOW_TOOL = "summarize_window"
SUMMARY_SCHEMA_VERSION = "window-summary/1"
DAY_CHANGE_FLAG = Decimal("0.5")
"""A day whose spend or conversions move by at least this share versus the prior day is flagged."""
_MONEY = Decimal("0.01")
_RATIO = Decimal("0.0001")


class SummarizeWindowArgs(BaseModel):
    artifact_ids: list[str] = Field(description="performance_rows artifact ids, one per platform.")
    start_date: date
    end_date: date
    budgets_artifact_ids: list[str] = Field(
        default_factory=list,
        description="provider_result artifacts from list_campaigns; supplies daily budgets for pacing.",
    )


def _money(value: Decimal) -> str:
    return str(value.quantize(_MONEY, rounding=ROUND_HALF_UP))


def _ratio_str(numerator: Decimal | int | None, denominator: Decimal | int | None) -> str | None:
    if numerator is None or not denominator:
        return None
    return str((Decimal(numerator) / Decimal(denominator)).quantize(_RATIO, rounding=ROUND_HALF_UP))


def _change(current: Decimal, previous: Decimal) -> Decimal | None:
    return None if previous == 0 else (current - previous) / previous


def budgets_from_payload(payload: dict[str, JsonValue]) -> dict[str, Decimal]:
    """Daily budgets keyed by entity id from a list_campaigns provider result."""
    result = payload.get("result")
    campaigns = result.get("campaigns") if isinstance(result, dict) else None
    budgets: dict[str, Decimal] = {}
    for campaign in campaigns or []:
        if isinstance(campaign, dict) and campaign.get("daily_budget") not in (None, ""):
            budgets[str(campaign.get("id"))] = Decimal(str(campaign["daily_budget"]))
    return budgets


def summarize_rows(
    rows: list[PerformanceRow],
    *,
    start: date,
    end: date,
    budgets: dict[str, Decimal],
) -> dict[str, Any]:
    selected = [r for r in rows if start <= r.window.start <= end]
    if not selected:
        raise ComputeError("no rows fall inside the window")
    days = sorted({r.window.start for r in selected})
    total = aggregate(selected)
    entities: list[dict[str, Any]] = []
    for ref in sorted({r.entity_ref for r in selected}):
        own = [r for r in selected if r.entity_ref == ref]
        metrics = aggregate(own)
        active_days = len({r.window.start for r in own})
        average_daily = metrics.spend / active_days
        budget = budgets.get(ref)
        entities.append(
            {
                "entity_ref": ref,
                "entity_name": own[0].entity_name,
                "spend": _money(metrics.spend),
                "share_of_spend": _ratio_str(metrics.spend, total.spend),
                "conversions": None if metrics.conversions is None else str(metrics.conversions),
                "cpa": None if metrics.cpa is None else str(metrics.cpa),
                "roas": None if metrics.roas is None else str(metrics.roas),
                "ctr": None if metrics.ctr is None else str(metrics.ctr),
                "active_days": active_days,
                "average_daily_spend": _money(average_daily),
                "daily_budget": None if budget is None else _money(budget),
                "pacing": _ratio_str(average_daily, budget),
            }
        )
    entities.sort(key=lambda e: Decimal(e["spend"]), reverse=True)
    daily: list[dict[str, Any]] = []
    previous: dict[str, Decimal] | None = None
    for day in days:
        day_metrics = aggregate([r for r in selected if r.window.start == day])
        point = {"spend": day_metrics.spend, "conversions": day_metrics.conversions or Decimal(0)}
        entry: dict[str, Any] = {
            "date": day.isoformat(),
            "spend": _money(point["spend"]),
            "conversions": str(point["conversions"]),
        }
        if previous is not None:
            for metric in ("spend", "conversions"):
                change = _change(point[metric], previous[metric])
                entry[f"{metric}_change"] = None if change is None else _ratio_str(change, 1)
                if change is not None and abs(change) >= DAY_CHANGE_FLAG:
                    entry.setdefault("flags", []).append(
                        f"{metric}_moved_{'up' if change > 0 else 'down'}"
                    )
        daily.append(entry)
        previous = point
    return {
        "requested_window": f"{start.isoformat()}..{end.isoformat()}",
        "covered_window": f"{days[0].isoformat()}..{days[-1].isoformat()}",
        "days_covered": len(days),
        "currency": selected[0].currency,
        "totals": {
            "spend": _money(total.spend),
            "impressions": total.impressions,
            "clicks": total.clicks,
            "conversions": None if total.conversions is None else str(total.conversions),
            "cpa": None if total.cpa is None else str(total.cpa),
            "roas": None if total.roas is None else str(total.roas),
            "ctr": None if total.ctr is None else str(total.ctr),
        },
        "entities": entities,
        "daily": daily,
        "flagged_days": [d["date"] for d in daily if d.get("flags")],
        "over_budget": [
            e["entity_ref"] for e in entities if e["pacing"] and Decimal(e["pacing"]) > 1
        ],
    }


def run_summarize_window(artifacts: ArtifactStore, args: SummarizeWindowArgs) -> dict[str, Any]:
    if args.end_date < args.start_date:
        raise ComputeError("window end precedes start")
    budgets: dict[str, Decimal] = {}
    for artifact_id in args.budgets_artifact_ids:
        budgets.update(budgets_from_payload(artifacts.read(artifact_id).payload))
    platforms: dict[str, Any] = {}
    for artifact_id in args.artifact_ids:
        record = artifacts.read(artifact_id)
        if record.metadata.kind != "performance_rows":
            raise ComputeError(f"{artifact_id} is not a performance_rows artifact")
        rows = rows_from_payload(record.payload)
        summary = summarize_rows(rows, start=args.start_date, end=args.end_date, budgets=budgets)
        summary["source_artifact"] = artifact_id
        summary["missing_fields"] = list(record.payload.get("missing_fields") or [])
        platforms[record.metadata.platform or rows[0].platform.value] = summary
    metadata = artifacts.write_json(
        "analysis",
        {"schema_version": SUMMARY_SCHEMA_VERSION, "platforms": platforms},
        schema_version=SUMMARY_SCHEMA_VERSION,
        requested_window=f"{args.start_date.isoformat()}..{args.end_date.isoformat()}",
        tool_name=SUMMARIZE_WINDOW_TOOL,
    )
    return {"artifact_id": metadata.artifact_id, "platforms": platforms}


def build_summarize_window_tool(artifacts: ArtifactStore) -> BaseTool:
    def _run(**kwargs: Any) -> str:
        try:
            args = SummarizeWindowArgs.model_validate(kwargs)
            return json.dumps(run_summarize_window(artifacts, args))
        except (
            ArtifactError,
            ComputeError,
            NormalizationError,
            ValidationError,
            ValueError,
        ) as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})

    return StructuredTool(
        name=SUMMARIZE_WINDOW_TOOL,
        description=(
            "Summarize one window from performance_rows artifacts: totals, per-entity spend share, "
            "CPA, ROAS, CTR, average daily spend and pacing against daily budgets (pass the "
            "list_campaigns artifacts), plus a daily series with day-over-day changes and flagged "
            "days. Use it for pacing, anomalies, and top-N questions inside a single window; use "
            "compare_periods for period-over-period change."
        ),
        args_schema=SummarizeWindowArgs,
        func=_run,
    )
