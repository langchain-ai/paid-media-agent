"""Deterministic analysis outputs. Every number here is computed by code, never by the model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import DataQualityFlag, EntityType, OpaqueAccountRef, Platform
from paid_media_agent.domain.metrics import MetricWindow

ANALYSIS_SCHEMA_VERSION = "period-comparison/1"
ANALYSIS_VERSION = "compute/1.0.0"

METRIC_NAMES: tuple[str, ...] = (
    "spend",
    "impressions",
    "clicks",
    "conversions",
    "conversion_value",
    "ctr",
    "cpc",
    "cpm",
    "cvr",
    "cpa",
    "roas",
)


class MetricSet(BaseModel):
    """Aggregated metrics for one entity or platform in one window."""

    model_config = ConfigDict(frozen=True)

    spend: Decimal
    impressions: int | None = None
    clicks: int | None = None
    conversions: Decimal | None = None
    conversion_value: Decimal | None = None
    ctr: Decimal | None = None
    cpc: Decimal | None = None
    cpm: Decimal | None = None
    cvr: Decimal | None = None
    cpa: Decimal | None = None
    roas: Decimal | None = None
    row_count: int = 0
    day_coverage: int = 0

    def value(self, metric: str) -> Decimal | int | None:
        result = getattr(self, metric)
        if isinstance(result, Decimal | int) or result is None:
            return result
        raise KeyError(metric)


class MetricDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    current: Decimal | None
    previous: Decimal | None
    absolute: Decimal | None
    relative: Decimal | None
    """Fraction (0.10 == +10%). None when the previous value is missing or zero."""


class EntityComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_type: EntityType
    entity_ref: str
    entity_name: str
    current: MetricSet
    previous: MetricSet
    deltas: tuple[MetricDelta, ...]
    quality_flags: tuple[DataQualityFlag, ...] = ()


class ReconciliationCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    detail: str


class PlatformComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    account_ref: OpaqueAccountRef
    currency: str
    entity_type: EntityType
    current_window: MetricWindow
    previous_window: MetricWindow
    current: MetricSet
    previous: MetricSet
    deltas: tuple[MetricDelta, ...]
    entities: tuple[EntityComparison, ...]
    missing_fields: tuple[str, ...] = ()
    quality_flags: tuple[DataQualityFlag, ...] = ()
    source_artifacts: tuple[str, ...] = ()
    reconciliation: tuple[ReconciliationCheck, ...] = ()


class PeriodComparison(BaseModel):
    """Versioned result of `compare_periods`. Serialized as an analysis artifact."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = ANALYSIS_SCHEMA_VERSION
    analysis_version: str = ANALYSIS_VERSION
    computed_at: datetime
    requested_current: MetricWindow
    requested_previous: MetricWindow
    platforms: tuple[PlatformComparison, ...]
    cross_platform_total: MetricSet | None = None
    cross_platform_previous: MetricSet | None = None
    total_suppressed_reason: str | None = None
    unavailable_sources: tuple[str, ...] = ()

    @property
    def reconciled(self) -> bool:
        return all(check.passed for p in self.platforms for check in p.reconciliation)


class PlatformHeadline(BaseModel):
    """Compact per-platform view for the model and surfaces."""

    model_config = ConfigDict(frozen=True)

    platform: Platform
    account_ref: OpaqueAccountRef
    currency: str
    spend_current: str
    spend_previous: str
    spend_change: str
    conversions_current: str
    conversions_previous: str
    cpa_current: str
    cpa_previous: str
    roas_current: str
    roas_previous: str
    entity_count: int
    missing_fields: tuple[str, ...]
    quality_flags: tuple[DataQualityFlag, ...]
    attention: tuple[str, ...]
    """Code-selected entities that moved most, as short strings with exact values."""


class AnalysisSummary(BaseModel):
    """What the model receives. It cites this instead of recomputing anything."""

    model_config = ConfigDict(frozen=True)

    kind: str = "analysis_summary"
    artifact_id: str
    schema_version: str
    analysis_version: str
    current_window: str
    previous_window: str
    platforms: tuple[PlatformHeadline, ...]
    cross_platform_total: str | None
    total_suppressed_reason: str | None
    unavailable_sources: tuple[str, ...]
    reconciled: bool
    source_artifacts: tuple[str, ...] = Field(default_factory=tuple)
    notes: tuple[str, ...] = ()
