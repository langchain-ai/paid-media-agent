"""Platform-aware normalization into `PerformanceRow`. Unknown metrics stay missing."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal, InvalidOperation

from paid_media_agent.domain.common import DataQualityFlag, EntityType, JsonValue, Platform
from paid_media_agent.domain.metrics import MetricWindow, PerformanceRow

ROWS_SCHEMA_VERSION = "performance-rows/1"

_SPEND_KEYS: dict[Platform, tuple[tuple[str, Decimal], ...]] = {
    Platform.GOOGLE_ADS: (
        ("cost_micros", Decimal(1_000_000)),
        ("spend", Decimal(1)),
        ("cost", Decimal(1)),
    ),
    Platform.META_ADS: (("spend", Decimal(1)),),
    Platform.REDDIT_ADS: (("spend_micros", Decimal(1_000_000)), ("spend", Decimal(1))),
    Platform.LINKEDIN_ADS: (("spend", Decimal(1)), ("costInLocalCurrency", Decimal(1))),
    Platform.X_ADS: (("spend_micros", Decimal(1_000_000)), ("spend", Decimal(1))),
    Platform.OPENAI_ADS: (("spend", Decimal(1)),),
}
_CONVERSION_KEYS = ("conversions", "purchases", "results")
_VALUE_KEYS = ("conversion_value", "conversions_value", "value", "purchase_value", "action_values")
_ENTITY_ID_KEYS = ("campaign_id", "ad_group_id", "ad_id", "entity_id", "id")
_ENTITY_NAME_KEYS = ("campaign_name", "ad_group_name", "ad_name", "entity_name", "name")


class NormalizationError(Exception):
    pass


def _decimal(value: JsonValue) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value: JsonValue) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _first(row: Mapping[str, JsonValue], keys: Sequence[str]) -> JsonValue:
    for key in keys:
        if key in row and row[key] is not None:
            return row[key]
    return None


def normalize_rows(
    *,
    platform: Platform,
    account_ref: str,
    currency: str,
    timezone: str,
    rows: Sequence[Mapping[str, JsonValue]],
    entity_type: EntityType,
    entity_names: Mapping[str, str] | None = None,
    data_complete_through: date | None,
) -> tuple[list[PerformanceRow], tuple[str, ...]]:
    """Return normalized rows and the metric fields that were missing in every source row."""
    spend_keys = _SPEND_KEYS[platform]
    normalized: list[PerformanceRow] = []
    seen_metric: dict[str, bool] = {
        "impressions": False,
        "clicks": False,
        "conversions": False,
        "conversion_value": False,
    }
    for raw in rows:
        day_raw = raw.get("date") or raw.get("day") or raw.get("date_start")
        if not isinstance(day_raw, str):
            raise NormalizationError("row without a date")
        day = date.fromisoformat(day_raw)
        spend: Decimal | None = None
        for key, divisor in spend_keys:
            candidate = _decimal(raw.get(key))
            if candidate is not None:
                spend = candidate / divisor
                break
        if spend is None:
            raise NormalizationError("row without spend")
        entity_ref = _first(raw, _ENTITY_ID_KEYS)
        if entity_ref is None:
            raise NormalizationError("row without an entity id")
        entity_ref_str = str(entity_ref)
        name = _first(raw, _ENTITY_NAME_KEYS)
        entity_name = (
            str(name)
            if name is not None
            else (entity_names or {}).get(entity_ref_str, entity_ref_str)
        )
        impressions = _int(raw.get("impressions"))
        clicks = _int(raw.get("clicks") or raw.get("link_clicks"))
        conversions = _decimal(_first(raw, _CONVERSION_KEYS))
        conversion_value = _decimal(_first(raw, _VALUE_KEYS))
        for metric, present in (
            ("impressions", impressions is not None),
            ("clicks", clicks is not None),
            ("conversions", conversions is not None),
            ("conversion_value", conversion_value is not None),
        ):
            seen_metric[metric] = seen_metric[metric] or present
        flags: list[DataQualityFlag] = []
        if data_complete_through is not None and day > data_complete_through:
            flags.append(DataQualityFlag.INCOMPLETE_WINDOW)
        if conversion_value is None or conversions is None:
            flags.append(DataQualityFlag.MISSING_METRIC)
        normalized.append(
            PerformanceRow(
                platform=platform,
                account_ref=account_ref,
                entity_type=entity_type,
                entity_ref=entity_ref_str,
                entity_name=entity_name,
                window=MetricWindow(
                    start=day,
                    end=day,
                    timezone=timezone,
                    is_complete=data_complete_through is None or day <= data_complete_through,
                ),
                currency=currency,
                spend=spend.quantize(Decimal("0.000001")),
                impressions=impressions,
                clicks=clicks,
                conversions=conversions,
                conversion_value=conversion_value,
                source_fields=dict(raw),
                quality_flags=tuple(flags),
            )
        )
    missing = tuple(metric for metric, present in seen_metric.items() if rows and not present)
    return normalized, missing


def rows_to_payload(rows: Sequence[PerformanceRow]) -> dict[str, JsonValue]:
    return {
        "schema_version": ROWS_SCHEMA_VERSION,
        "rows": [row.model_dump(mode="json") for row in rows],
    }


def rows_from_payload(payload: Mapping[str, JsonValue]) -> list[PerformanceRow]:
    if payload.get("schema_version") != ROWS_SCHEMA_VERSION:
        raise NormalizationError("artifact is not a performance-rows artifact")
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise NormalizationError("artifact rows are malformed")
    return [PerformanceRow.model_validate(item) for item in raw_rows]
