"""Versioned report payload. The model writes bounded narrative; code renders everything else."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import Platform

REPORT_SCHEMA_VERSION = "report/1"

NARRATIVE_MAX = 1200


class ReportScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    accounts: tuple[str, ...]
    platforms: tuple[Platform, ...]
    current_window: str
    previous_window: str
    currency: str | None
    source_coverage: str


class ScorecardRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    definition: str
    current: str
    previous: str
    change: str
    raw_current: str | None
    raw_previous: str | None


class PlatformSection(BaseModel):
    model_config = ConfigDict(frozen=True)

    platform: Platform
    account_ref: str
    currency: str
    rows: tuple[ScorecardRow, ...]
    drivers: tuple[str, ...]
    missing_fields: tuple[str, ...]
    quality_flags: tuple[str, ...]


class Recommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    target: str = Field(max_length=200)
    action: str = Field(max_length=400)
    evidence: str = Field(max_length=NARRATIVE_MAX)
    expected_effect: str = Field(max_length=400)
    confidence: str = Field(pattern=r"^(low|medium|high)$")
    measurement: str = Field(max_length=400)
    reversal: str = Field(max_length=400)


class ReportProvenance(BaseModel):
    model_config = ConfigDict(frozen=True)

    analysis_artifact_id: str
    source_artifacts: tuple[str, ...]
    analysis_version: str
    analysis_schema_version: str
    generated_at: datetime
    report_schema_version: str = REPORT_SCHEMA_VERSION


class ReportPayload(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_version: str = REPORT_SCHEMA_VERSION
    report_id: str
    title: str = Field(max_length=160)
    scope: ReportScope
    executive_summary: str = Field(max_length=NARRATIVE_MAX)
    scorecard: tuple[ScorecardRow, ...]
    total_suppressed_reason: str | None
    platform_sections: tuple[PlatformSection, ...]
    recommendations: tuple[Recommendation, ...]
    data_quality: tuple[str, ...]
    unavailable_sources: tuple[str, ...]
    provenance: ReportProvenance
