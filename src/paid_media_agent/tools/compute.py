"""Deterministic period comparison. All arithmetic, grouping, and reconciliation live here."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from paid_media_agent.domain.analysis import (
    METRIC_NAMES,
    AnalysisSummary,
    EntityComparison,
    MetricDelta,
    MetricSet,
    PeriodComparison,
    PlatformComparison,
    PlatformHeadline,
    ReconciliationCheck,
)
from paid_media_agent.domain.common import DataQualityFlag, EntityType, JsonValue, Platform
from paid_media_agent.domain.format import format_count, format_money, format_percent, format_ratio
from paid_media_agent.domain.metrics import MetricWindow, PerformanceRow

_RATIO_QUANTUM = Decimal("0.000001")
_MONEY_QUANTUM = Decimal("0.000001")


class ComputeError(Exception):
    pass


def _q(value: Decimal) -> Decimal:
    return value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_UP)


def _ratio(
    numerator: Decimal | int | None, denominator: Decimal | int | None, scale: Decimal = Decimal(1)
) -> Decimal | None:
    """Return numerator / denominator * scale, or None for missing inputs or a zero denominator."""
    if numerator is None or denominator is None:
        return None
    denom = Decimal(denominator)
    if denom == 0:
        return None
    return _q(Decimal(numerator) / denom * scale)


def _sum_optional_int(values: Iterable[int | None]) -> int | None:
    total = 0
    seen = False
    for value in values:
        if value is None:
            continue
        seen = True
        total += value
    return total if seen else None


def _sum_optional_decimal(values: Iterable[Decimal | None]) -> Decimal | None:
    total = Decimal(0)
    seen = False
    for value in values:
        if value is None:
            continue
        seen = True
        total += value
    return total.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP) if seen else None


def aggregate(rows: Sequence[PerformanceRow]) -> MetricSet:
    """Sum raw metrics then derive ratios. A metric missing from every row stays None."""
    spend = sum((row.spend for row in rows), Decimal(0)).quantize(
        _MONEY_QUANTUM, rounding=ROUND_HALF_UP
    )
    impressions = _sum_optional_int(row.impressions for row in rows)
    clicks = _sum_optional_int(row.clicks for row in rows)
    conversions = _sum_optional_decimal(row.conversions for row in rows)
    conversion_value = _sum_optional_decimal(row.conversion_value for row in rows)
    days = {row.window.start for row in rows}
    return MetricSet(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        conversion_value=conversion_value,
        ctr=_ratio(clicks, impressions),
        cpc=_ratio(spend, clicks),
        cpm=_ratio(spend, impressions, Decimal(1000)),
        cvr=_ratio(conversions, clicks),
        cpa=_ratio(spend, conversions),
        roas=_ratio(conversion_value, spend),
        row_count=len(rows),
        day_coverage=len(days),
    )


def deltas(current: MetricSet, previous: MetricSet) -> tuple[MetricDelta, ...]:
    result: list[MetricDelta] = []
    for metric in METRIC_NAMES:
        cur = current.value(metric)
        prev = previous.value(metric)
        cur_d = Decimal(cur) if cur is not None else None
        prev_d = Decimal(prev) if prev is not None else None
        absolute = _q(cur_d - prev_d) if cur_d is not None and prev_d is not None else None
        relative = None
        if absolute is not None and prev_d is not None and prev_d != 0:
            relative = _q(absolute / prev_d)
        result.append(
            MetricDelta(
                metric=metric, current=cur_d, previous=prev_d, absolute=absolute, relative=relative
            )
        )
    return tuple(result)


def _window_rows(rows: Sequence[PerformanceRow], window: MetricWindow) -> list[PerformanceRow]:
    return [row for row in rows if window.contains(row.window.start)]


def _entity_flags(
    rows: Sequence[PerformanceRow], window: MetricWindow
) -> tuple[DataQualityFlag, ...]:
    flags: set[DataQualityFlag] = set()
    days = {row.window.start for row in rows}
    if len(days) != len(rows):
        flags.add(DataQualityFlag.DUPLICATE_ROWS)
    if len(days) < window.day_count or any(not row.window.is_complete for row in rows):
        flags.add(DataQualityFlag.INCOMPLETE_WINDOW)
    if any(DataQualityFlag.MISSING_METRIC in row.quality_flags for row in rows):
        flags.add(DataQualityFlag.MISSING_METRIC)
    return tuple(sorted(flags))


def compare_platform(
    *,
    platform: Platform,
    account_ref: str,
    rows: Sequence[PerformanceRow],
    current_window: MetricWindow,
    previous_window: MetricWindow,
    entity_type: EntityType,
    source_artifacts: Sequence[str],
    provider_totals: dict[str, JsonValue] | None = None,
    missing_fields: Sequence[str] = (),
) -> PlatformComparison:
    if not rows:
        raise ComputeError(f"no rows for {platform.value}")
    currencies = {row.currency for row in rows}
    if len(currencies) != 1:
        raise ComputeError(f"mixed currencies in {platform.value} rows")
    timezones = {row.window.timezone for row in rows}
    if len(timezones) != 1:
        raise ComputeError(f"mixed timezones in {platform.value} rows")
    currency = next(iter(currencies))
    timezone = next(iter(timezones))
    if entity_type is not EntityType.ACCOUNT and any(
        row.entity_type is not entity_type for row in rows
    ):
        raise ComputeError("rows do not match the requested entity grain")

    current_rows = _window_rows(rows, current_window)
    previous_rows = _window_rows(rows, previous_window)
    by_entity_current: dict[str, list[PerformanceRow]] = defaultdict(list)
    by_entity_previous: dict[str, list[PerformanceRow]] = defaultdict(list)
    names: dict[str, str] = {}
    for row in current_rows:
        by_entity_current[row.entity_ref].append(row)
        names[row.entity_ref] = row.entity_name
    for row in previous_rows:
        by_entity_previous[row.entity_ref].append(row)
        names.setdefault(row.entity_ref, row.entity_name)

    entities: list[EntityComparison] = []
    platform_flags: set[DataQualityFlag] = set()
    for entity_ref in sorted(names):
        cur_rows = by_entity_current.get(entity_ref, [])
        prev_rows = by_entity_previous.get(entity_ref, [])
        cur = aggregate(cur_rows)
        prev = aggregate(prev_rows)
        flags = set(_entity_flags(cur_rows, current_window)) | set(
            _entity_flags(prev_rows, previous_window)
        )
        if not cur_rows or not prev_rows:
            flags.add(DataQualityFlag.PARTIAL_SOURCE)
        platform_flags |= flags
        entities.append(
            EntityComparison(
                entity_type=entity_type,
                entity_ref=entity_ref,
                entity_name=names[entity_ref],
                current=cur,
                previous=prev,
                deltas=deltas(cur, prev),
                quality_flags=tuple(sorted(flags)),
            )
        )

    current = aggregate(current_rows)
    previous = aggregate(previous_rows)
    actual_current_days = {row.window.start for row in current_rows}
    actual_previous_days = {row.window.start for row in previous_rows}
    current_complete = (
        len(actual_current_days) == current_window.day_count
        and all(row.window.is_complete for row in current_rows)
        and DataQualityFlag.INCOMPLETE_WINDOW not in platform_flags
    )
    previous_complete = len(actual_previous_days) == previous_window.day_count and all(
        row.window.is_complete for row in previous_rows
    )
    if not current_complete or not previous_complete:
        platform_flags.add(DataQualityFlag.INCOMPLETE_WINDOW)
    if missing_fields:
        platform_flags.add(DataQualityFlag.MISSING_METRIC)

    checks: list[ReconciliationCheck] = []
    entity_spend = sum((e.current.spend for e in entities), Decimal(0))
    checks.append(
        ReconciliationCheck(
            name="entity_rows_sum_to_platform_spend",
            passed=entity_spend == current.spend,
            detail=f"entities {entity_spend} vs platform {current.spend}",
        )
    )
    if provider_totals is not None:
        all_rows = current_rows + previous_rows
        provider_spend = provider_totals.get("spend")
        if provider_spend is not None:
            expected = Decimal(str(provider_spend)).quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
            actual = sum((row.spend for row in all_rows), Decimal(0)).quantize(
                _MONEY_QUANTUM, rounding=ROUND_HALF_UP
            )
            checks.append(
                ReconciliationCheck(
                    name="rows_reconcile_to_provider_spend",
                    passed=expected == actual,
                    detail=f"provider {expected} vs rows {actual}",
                )
            )
        provider_rows = provider_totals.get("row_count")
        if provider_rows is not None:
            checks.append(
                ReconciliationCheck(
                    name="row_count_matches_provider",
                    passed=int(str(provider_rows)) == len(all_rows),
                    detail=f"provider {provider_rows} vs rows {len(all_rows)}",
                )
            )

    return PlatformComparison(
        platform=platform,
        account_ref=account_ref,
        currency=currency,
        entity_type=entity_type,
        current_window=MetricWindow(
            start=current_window.start,
            end=current_window.end,
            timezone=timezone,
            is_complete=current_complete,
        ),
        previous_window=MetricWindow(
            start=previous_window.start,
            end=previous_window.end,
            timezone=timezone,
            is_complete=previous_complete,
        ),
        current=current,
        previous=previous,
        deltas=deltas(current, previous),
        entities=tuple(entities),
        missing_fields=tuple(missing_fields),
        quality_flags=tuple(sorted(platform_flags)),
        source_artifacts=tuple(source_artifacts),
        reconciliation=tuple(checks),
    )


def _combine(metric_sets: Sequence[MetricSet]) -> MetricSet:
    spend = sum((m.spend for m in metric_sets), Decimal(0))
    impressions = _sum_optional_int(m.impressions for m in metric_sets)
    clicks = _sum_optional_int(m.clicks for m in metric_sets)
    conversions = _sum_optional_decimal(m.conversions for m in metric_sets)
    conversion_value = _sum_optional_decimal(m.conversion_value for m in metric_sets)
    return MetricSet(
        spend=spend,
        impressions=impressions,
        clicks=clicks,
        conversions=conversions,
        conversion_value=conversion_value,
        ctr=_ratio(clicks, impressions),
        cpc=_ratio(spend, clicks),
        cpm=_ratio(spend, impressions, Decimal(1000)),
        cvr=_ratio(conversions, clicks),
        cpa=_ratio(spend, conversions),
        roas=_ratio(conversion_value, spend),
        row_count=sum(m.row_count for m in metric_sets),
        day_coverage=max((m.day_coverage for m in metric_sets), default=0),
    )


def compare_periods(
    *,
    platforms: Sequence[PlatformComparison],
    requested_current: MetricWindow,
    requested_previous: MetricWindow,
    unavailable_sources: Sequence[str] = (),
    now: datetime | None = None,
) -> PeriodComparison:
    """Combine platform comparisons. The total exists only when every source is compatible."""
    suppressed: str | None = None
    if not platforms:
        suppressed = "no platform data"
    elif unavailable_sources:
        suppressed = "one or more requested sources are unavailable"
    else:
        currencies = {p.currency for p in platforms}
        if len(currencies) != 1:
            suppressed = f"mixed currencies: {', '.join(sorted(currencies))}"
        elif any(
            not p.current_window.is_complete or not p.previous_window.is_complete for p in platforms
        ):
            suppressed = "at least one platform window is incomplete"
        elif any(DataQualityFlag.MISSING_METRIC in p.quality_flags for p in platforms):
            suppressed = "at least one platform is missing a metric field"
        elif len({(p.current_window.start, p.current_window.end) for p in platforms}) != 1:
            suppressed = "platform windows differ"
    total = None
    total_previous = None
    if suppressed is None:
        total = _combine([p.current for p in platforms])
        total_previous = _combine([p.previous for p in platforms])
    return PeriodComparison(
        computed_at=now or datetime.now(UTC),
        requested_current=requested_current,
        requested_previous=requested_previous,
        platforms=tuple(platforms),
        cross_platform_total=total,
        cross_platform_previous=total_previous,
        total_suppressed_reason=suppressed,
        unavailable_sources=tuple(unavailable_sources),
    )


def _window_label(window: MetricWindow) -> str:
    suffix = "" if window.is_complete else " (incomplete)"
    return f"{window.start.isoformat()}..{window.end.isoformat()} {window.timezone}{suffix}"


def _attention_lines(platform: PlatformComparison, limit: int = 3) -> tuple[str, ...]:
    """Code picks the largest absolute spend movers and states exact values."""
    scored = []
    for entity in platform.entities:
        spend_delta = next(d for d in entity.deltas if d.metric == "spend")
        magnitude = abs(spend_delta.absolute) if spend_delta.absolute is not None else Decimal(0)
        scored.append((magnitude, entity, spend_delta))
    scored.sort(key=lambda item: (-item[0], item[1].entity_ref))
    lines: list[str] = []
    for _, entity, spend_delta in scored[:limit]:
        cpa_delta = next(d for d in entity.deltas if d.metric == "cpa")
        flags = (
            f" flags={','.join(f.value for f in entity.quality_flags)}"
            if entity.quality_flags
            else ""
        )
        lines.append(
            f"{entity.entity_name} [{entity.entity_ref}]: spend "
            f"{format_money(entity.current.spend, platform.currency)} vs "
            f"{format_money(entity.previous.spend, platform.currency)} ({format_percent(spend_delta.relative)}), "
            f"CPA {format_money(entity.current.cpa, platform.currency)} vs "
            f"{format_money(entity.previous.cpa, platform.currency)} ({format_percent(cpa_delta.relative)}){flags}"
        )
    return tuple(lines)


def summarize(comparison: PeriodComparison, artifact_id: str) -> AnalysisSummary:
    headlines: list[PlatformHeadline] = []
    for platform in comparison.platforms:
        spend_delta = next(d for d in platform.deltas if d.metric == "spend")
        headlines.append(
            PlatformHeadline(
                platform=platform.platform,
                account_ref=platform.account_ref,
                currency=platform.currency,
                spend_current=format_money(platform.current.spend, platform.currency),
                spend_previous=format_money(platform.previous.spend, platform.currency),
                spend_change=format_percent(spend_delta.relative),
                conversions_current=format_count(platform.current.conversions),
                conversions_previous=format_count(platform.previous.conversions),
                cpa_current=format_money(platform.current.cpa, platform.currency),
                cpa_previous=format_money(platform.previous.cpa, platform.currency),
                roas_current=format_ratio(platform.current.roas),
                roas_previous=format_ratio(platform.previous.roas),
                entity_count=len(platform.entities),
                days_covered=(
                    f"{platform.current.day_coverage}/{platform.current_window.day_count} current, "
                    f"{platform.previous.day_coverage}/{platform.previous_window.day_count} previous"
                ),
                missing_fields=platform.missing_fields,
                quality_flags=platform.quality_flags,
                attention=_attention_lines(platform),
            )
        )
    total = None
    if comparison.cross_platform_total is not None and comparison.platforms:
        currency = comparison.platforms[0].currency
        total = format_money(comparison.cross_platform_total.spend, currency)
    notes = ["Values are computed by code from the cited artifacts. Do not recompute them."]
    if comparison.total_suppressed_reason:
        notes.append(f"Cross-platform total suppressed: {comparison.total_suppressed_reason}.")
    return AnalysisSummary(
        artifact_id=artifact_id,
        schema_version=comparison.schema_version,
        analysis_version=comparison.analysis_version,
        current_window=_window_label(comparison.requested_current),
        previous_window=_window_label(comparison.requested_previous),
        platforms=tuple(headlines),
        cross_platform_total=total,
        total_suppressed_reason=comparison.total_suppressed_reason,
        unavailable_sources=comparison.unavailable_sources,
        reconciled=comparison.reconciled,
        source_artifacts=tuple(a for p in comparison.platforms for a in p.source_artifacts),
        notes=tuple(notes),
    )
