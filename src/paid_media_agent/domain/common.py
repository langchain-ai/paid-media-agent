"""Shared enums and scalar types used across the domain."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

JsonValue = Any
"""JSON-compatible value. Pydantic validates structure at the model boundary."""


class Platform(StrEnum):
    GOOGLE_ADS = "google_ads"
    META_ADS = "meta_ads"
    REDDIT_ADS = "reddit_ads"
    LINKEDIN_ADS = "linkedin_ads"
    X_ADS = "x_ads"
    OPENAI_ADS = "openai_ads"


PIPEBOARD_PLATFORMS: tuple[Platform, ...] = (
    Platform.GOOGLE_ADS,
    Platform.META_ADS,
    Platform.REDDIT_ADS,
)
"""Platforms reached through Pipeboard MCP. The others use direct adapters in tools/direct."""


class EntityType(StrEnum):
    ACCOUNT = "account"
    CAMPAIGN = "campaign"
    AD_GROUP = "ad_group"
    AD = "ad"
    KEYWORD = "keyword"
    AUDIENCE = "audience"
    CREATIVE = "creative"


class DataQualityFlag(StrEnum):
    INCOMPLETE_WINDOW = "incomplete_window"
    MISSING_METRIC = "missing_metric"
    PARTIAL_SOURCE = "partial_source"
    SOURCE_UNAVAILABLE = "source_unavailable"
    CURRENCY_MISMATCH = "currency_mismatch"
    TIMEZONE_MISMATCH = "timezone_mismatch"
    DUPLICATE_ROWS = "duplicate_rows"
    SUPPRESSED_TOTAL = "suppressed_total"
    ATTRIBUTION_DIFFERS = "attribution_differs"
    STALE_CATALOG = "stale_catalog"


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


OpaqueAccountRef = str
"""Public account alias. Provider account ids never leave host code."""
