"""Common performance data model. Missing metrics stay `None`; they are never zero."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from paid_media_agent.domain.common import (
    DataQualityFlag,
    EntityType,
    JsonValue,
    OpaqueAccountRef,
    Platform,
)


class MetricWindow(BaseModel):
    """Inclusive date window in one timezone with an explicit completeness flag."""

    model_config = ConfigDict(frozen=True)

    start: date
    end: date
    timezone: str
    is_complete: bool

    @model_validator(mode="after")
    def _ordered(self) -> MetricWindow:
        if self.end < self.start:
            raise ValueError("window end precedes start")
        return self

    @property
    def day_count(self) -> int:
        return (self.end - self.start).days + 1

    def contains(self, day: date) -> bool:
        return self.start <= day <= self.end

    def days(self) -> tuple[date, ...]:
        return tuple(self.start + timedelta(days=i) for i in range(self.day_count))

    def same_length(self, other: MetricWindow) -> bool:
        return self.day_count == other.day_count


class PerformanceRow(BaseModel):
    """One entity-day (or entity-window) observation normalized from a provider read."""

    model_config = ConfigDict(frozen=True)

    platform: Platform
    account_ref: OpaqueAccountRef
    entity_type: EntityType
    entity_ref: str
    entity_name: str
    window: MetricWindow
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    spend: Decimal
    impressions: int | None = None
    clicks: int | None = None
    conversions: Decimal | None = None
    conversion_value: Decimal | None = None
    source_fields: dict[str, JsonValue] = Field(default_factory=dict)
    quality_flags: tuple[DataQualityFlag, ...] = ()
