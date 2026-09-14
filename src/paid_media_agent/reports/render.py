from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from importlib import import_module
from pathlib import Path
from typing import Protocol

from paid_media_agent.domain.analysis import (
    MetricDelta,
    MetricSet,
    PeriodComparison,
    PlatformComparison,
)
from paid_media_agent.domain.format import format_count, format_money, format_percent, format_ratio
from paid_media_agent.domain.presentation import ReportSummary
from paid_media_agent.domain.reports import (
    PlatformSection,
    Recommendation,
    ReportPayload,
    ReportProvenance,
    ReportScope,
    ScorecardRow,
)

_DEFINITIONS: dict[str, str] = {
    "spend": "Platform-reported cost in account currency",
    "impressions": "Platform-reported impressions",
    "clicks": "Platform-reported clicks",
    "conversions": "Platform-attributed conversions (per-platform attribution)",
    "conversion_value": "Platform-attributed conversion value",
    "ctr": "clicks / impressions",
    "cpc": "spend / clicks",
    "cpm": "spend / impressions * 1000",
    "cvr": "conversions / clicks",
    "cpa": "spend / conversions",
    "roas": "conversion_value / spend",
}
_SCORECARD_METRICS = (
    "spend",
    "impressions",
    "clicks",
    "conversions",
    "conversion_value",
    "ctr",
    "cpc",
    "cpa",
    "roas",
)


def _format_metric(metric: str, value: Decimal | int | None, currency: str) -> str:
    if value is None:
        return "unavailable"
    if metric in ("spend", "cpc", "cpm", "cpa", "conversion_value"):
        return format_money(Decimal(value), currency)
    if metric in ("impressions", "clicks", "conversions"):
        return format_count(value)
    if metric in ("ctr", "cvr"):
        return format_percent(Decimal(value), places=2).lstrip("+")
    return format_ratio(Decimal(value))


def _raw(value: Decimal | int | None) -> str | None:
    return None if value is None else str(value)


def _rows(
    current: MetricSet, previous: MetricSet, deltas: tuple[MetricDelta, ...], currency: str
) -> tuple[ScorecardRow, ...]:
    by_metric = {d.metric: d for d in deltas}
    rows: list[ScorecardRow] = []
    for metric in _SCORECARD_METRICS:
        delta = by_metric[metric]
        rows.append(
            ScorecardRow(
                metric=metric,
                definition=_DEFINITIONS[metric],
                current=_format_metric(metric, current.value(metric), currency),
                previous=_format_metric(metric, previous.value(metric), currency),
                change=format_percent(delta.relative),
                raw_current=_raw(current.value(metric)),
                raw_previous=_raw(previous.value(metric)),
            )
        )
    return tuple(rows)


def _drivers(platform: PlatformComparison, limit: int = 3) -> tuple[str, ...]:
    scored = []
    for entity in platform.entities:
        spend_delta = next(d for d in entity.deltas if d.metric == "spend")
        magnitude = abs(spend_delta.absolute) if spend_delta.absolute is not None else Decimal(0)
        scored.append((magnitude, entity, spend_delta))
    scored.sort(key=lambda item: (-item[0], item[1].entity_ref))
    lines = []
    for _, entity, spend_delta in scored[:limit]:
        lines.append(
            f"{entity.entity_name} [{entity.entity_ref}]: spend {format_money(entity.current.spend, platform.currency)} "
            f"vs {format_money(entity.previous.spend, platform.currency)} ({format_percent(spend_delta.relative)}); "
            f"conversions {format_count(entity.current.conversions)} vs {format_count(entity.previous.conversions)}"
        )
    return tuple(lines)


def build_report_payload(
    comparison: PeriodComparison,
    *,
    analysis_artifact_id: str,
    title: str,
    executive_summary: str,
    recommendations: tuple[Recommendation, ...] = (),
    now: datetime | None = None,
) -> ReportPayload:
    platforms = comparison.platforms
    currencies = {p.currency for p in platforms}
    currency = next(iter(currencies)) if len(currencies) == 1 else None
    coverage = f"{len(platforms)} platform source(s) with data"
    if comparison.unavailable_sources:
        coverage += f"; unavailable: {', '.join(comparison.unavailable_sources)}"
    if (
        comparison.cross_platform_total is not None
        and comparison.cross_platform_previous is not None
        and currency
    ):
        from paid_media_agent.tools.compute import deltas as compute_deltas

        scorecard = _rows(
            comparison.cross_platform_total,
            comparison.cross_platform_previous,
            compute_deltas(comparison.cross_platform_total, comparison.cross_platform_previous),
            currency,
        )
    else:
        scorecard = ()
    sections = tuple(
        PlatformSection(
            platform=p.platform,
            account_ref=p.account_ref,
            currency=p.currency,
            rows=_rows(p.current, p.previous, p.deltas, p.currency),
            drivers=_drivers(p),
            missing_fields=p.missing_fields,
            quality_flags=tuple(f.value for f in p.quality_flags),
        )
        for p in platforms
    )
    data_quality: list[str] = []
    for p in platforms:
        if p.missing_fields:
            data_quality.append(
                f"{p.platform.value}: missing {', '.join(p.missing_fields)}; shown as unavailable"
            )
        if not p.current_window.is_complete:
            data_quality.append(f"{p.platform.value}: current window incomplete")
        if not p.previous_window.is_complete:
            data_quality.append(f"{p.platform.value}: comparison window incomplete")
        failed = [c.name for c in p.reconciliation if not c.passed]
        if failed:
            data_quality.append(
                f"{p.platform.value}: reconciliation failed for {', '.join(failed)}"
            )
    if comparison.total_suppressed_reason:
        data_quality.append(
            f"cross-platform total suppressed: {comparison.total_suppressed_reason}"
        )
    if len(platforms) > 1:
        data_quality.append(
            "conversions use each platform's own attribution; they are not deduplicated people"
        )
    if not data_quality:
        data_quality.append("all sources complete and reconciled")
    generated = now or datetime.now(UTC)
    return ReportPayload(
        report_id=f"rpt_{secrets.token_hex(6)}",
        title=title,
        scope=ReportScope(
            accounts=tuple(p.account_ref for p in platforms),
            platforms=tuple(p.platform for p in platforms),
            current_window=f"{comparison.requested_current.start.isoformat()}..{comparison.requested_current.end.isoformat()}",
            previous_window=f"{comparison.requested_previous.start.isoformat()}..{comparison.requested_previous.end.isoformat()}",
            currency=currency,
            source_coverage=coverage,
        ),
        executive_summary=executive_summary,
        scorecard=scorecard,
        total_suppressed_reason=comparison.total_suppressed_reason,
        platform_sections=sections,
        recommendations=recommendations,
        data_quality=tuple(data_quality),
        unavailable_sources=comparison.unavailable_sources,
        provenance=ReportProvenance(
            analysis_artifact_id=analysis_artifact_id,
            source_artifacts=tuple(a for p in platforms for a in p.source_artifacts),
            analysis_version=comparison.analysis_version,
            analysis_schema_version=comparison.schema_version,
            generated_at=generated,
        ),
    )


def reconcile_report(payload: ReportPayload, comparison: PeriodComparison) -> tuple[str, ...]:
    problems: list[str] = []
    by_account = {(p.platform, p.account_ref): p for p in comparison.platforms}
    for section in payload.platform_sections:
        source = by_account.get((section.platform, section.account_ref))
        if source is None:
            problems.append(f"{section.platform.value}: section without analysis source")
            continue
        for row in section.rows:
            expected_current = _raw(source.current.value(row.metric))
            expected_previous = _raw(source.previous.value(row.metric))
            if row.raw_current != expected_current or row.raw_previous != expected_previous:
                problems.append(
                    f"{section.platform.value}.{row.metric}: rendered values differ from analysis"
                )
            if row.current != _format_metric(
                row.metric, source.current.value(row.metric), section.currency
            ):
                problems.append(f"{section.platform.value}.{row.metric}: formatted value differs")
        if set(section.missing_fields) != set(source.missing_fields):
            problems.append(f"{section.platform.value}: missing fields not reproduced")
    missing_accounts = set(by_account) - {
        (s.platform, s.account_ref) for s in payload.platform_sections
    }
    if missing_accounts:
        problems.append(
            f"account sections missing: {', '.join(f'{p.value}/{a}' for p, a in sorted(missing_accounts))}"
        )
    if (comparison.total_suppressed_reason is None) != bool(payload.scorecard):
        problems.append("scorecard presence does not match total suppression")
    if set(payload.unavailable_sources) != set(comparison.unavailable_sources):
        problems.append("unavailable sources not reproduced")
    return tuple(problems)


class RenderedReport:
    def __init__(self, html_path: Path, pdf_path: Path | None, pdf_error: str | None) -> None:
        self.html_path = html_path
        self.pdf_path = pdf_path
        self.pdf_error = pdf_error


def pdf_renderer_available() -> tuple[bool, str]:
    import sys
    from contextlib import redirect_stdout

    try:
        with redirect_stdout(sys.stderr):
            import_module("weasyprint")
    except Exception as exc:
        return False, f"{type(exc).__name__}: WeasyPrint native libraries unavailable"
    return True, "ok"


class PdfEngine(Protocol):
    def available(self) -> tuple[bool, str]: ...

    def write_pdf(self, html: str, *, base_url: str, target: Path) -> None: ...


class HostPdfEngine:
    def available(self) -> tuple[bool, str]:
        return pdf_renderer_available()

    def write_pdf(self, html: str, *, base_url: str, target: Path) -> None:
        from weasyprint import HTML

        HTML(string=html, base_url=base_url).write_pdf(str(target))


@dataclass(frozen=True)
class ChartRow:
    platform: str
    account: str
    current: str
    previous: str
    current_width: str | None
    previous_width: str | None


@dataclass(frozen=True)
class ComparisonChart:
    metric: str
    title: str
    caption: str
    maximum: str
    rows: tuple[ChartRow, ...]


def _chart_value(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return value if value.is_finite() and value >= 0 else None


def comparison_charts(sections: tuple[PlatformSection, ...]) -> tuple[ComparisonChart, ...]:
    def width(value: Decimal | None, maximum: Decimal) -> str | None:
        if value is None:
            return None
        return format(value / maximum * 100 if maximum else Decimal(0), ".4f")

    currency_groups = [
        (currency, tuple(s for s in sections if s.currency == currency))
        for currency in sorted({s.currency for s in sections})
    ]
    groups = [
        (
            f"Spend · {currency}",
            "spend",
            sources,
            "",
        )
        for currency, sources in currency_groups
    ]
    groups.append(
        (
            "Attributed conversions",
            "conversions",
            sections,
            "Platform attribution; customers may overlap.",
        )
    )
    groups.extend(
        (
            f"Cost per conversion · {currency}",
            "cpa",
            sources,
            "",
        )
        for currency, sources in currency_groups
    )
    groups.append(("Return on ad spend", "roas", sections, ""))
    charts = []
    for title, metric, sources, caption in groups:
        entries = [
            (s, r, _chart_value(r.raw_current), _chart_value(r.raw_previous))
            for s in sources
            for r in s.rows
            if r.metric == metric
        ]
        values = [
            v for _, _, current, previous in entries for v in (current, previous) if v is not None
        ]
        if not values:
            continue
        maximum = max(values)

        charts.append(
            ComparisonChart(
                metric=metric,
                title=title,
                caption=caption,
                maximum=format_count(maximum),
                rows=tuple(
                    ChartRow(
                        platform=s.platform.value.replace("_", " ").title(),
                        account=s.account_ref,
                        current=r.current if current is not None else "unavailable",
                        previous=r.previous if previous is not None else "unavailable",
                        current_width=width(current, maximum),
                        previous_width=width(previous, maximum),
                    )
                    for s, r, current, previous in entries
                ),
            )
        )
    return tuple(charts)


def _format_window(window: str) -> str:
    try:
        start, end = (date.fromisoformat(part) for part in window.split(".."))
    except ValueError:
        return window
    if start == end:
        return f"{start:%b} {start.day}, {start.year}"
    if start.year != end.year:
        return f"{start:%b} {start.day}, {start.year}-{end:%b} {end.day}, {end.year}"
    if start.month != end.month:
        return f"{start:%b} {start.day}-{end:%b} {end.day}, {end.year}"
    return f"{start:%b} {start.day}-{end.day}, {end.year}"


class ReportRenderer:
    def __init__(
        self,
        out_dir: Path,
        templates_dir: Path | None = None,
        *,
        pdf_engine: PdfEngine | None = None,
    ) -> None:
        self._out = out_dir
        self._out.mkdir(parents=True, exist_ok=True)
        self._templates = templates_dir or Path(__file__).parent / "templates"
        self._pdf = pdf_engine or HostPdfEngine()

    def render_html(self, payload: ReportPayload) -> str:
        from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

        env = Environment(
            loader=FileSystemLoader(str(self._templates)),
            autoescape=select_autoescape(default=True, default_for_string=True),
            undefined=StrictUndefined,
        )
        env.filters["date_window"] = _format_window
        return env.get_template("report.html.j2").render(
            payload=payload, charts=comparison_charts(payload.platform_sections)
        )

    def render(self, payload: ReportPayload, *, want_pdf: bool = True) -> RenderedReport:
        html = self.render_html(payload)
        html_path = self._out / f"{payload.report_id}.html"
        html_path.write_text(html, encoding="utf-8")
        pdf_path: Path | None = None
        pdf_error: str | None = None
        if want_pdf:
            available, detail = self._pdf.available()
            if available:
                pdf_path = self._out / f"{payload.report_id}.pdf"
                self._pdf.write_pdf(html, base_url=str(self._out), target=pdf_path)
            else:
                pdf_error = detail
        return RenderedReport(html_path, pdf_path, pdf_error)


def report_summary(
    payload: ReportPayload, *, artifact_paths: tuple[str, ...], reconciled: bool
) -> ReportSummary:
    scorecard = tuple(
        (row.metric, f"{row.current} (prev {row.previous}, {row.change})")
        for row in payload.scorecard
    )
    lines = []
    for section in payload.platform_sections:
        spend = next(r for r in section.rows if r.metric == "spend")
        conv = next(r for r in section.rows if r.metric == "conversions")
        missing = f"; missing {', '.join(section.missing_fields)}" if section.missing_fields else ""
        lines.append(
            f"{section.platform.value} {section.account_ref}: spend {spend.current} ({spend.change}); "
            f"conversions {conv.current} vs {conv.previous}{missing}"
        )
    return ReportSummary(
        report_id=payload.report_id,
        title=payload.title,
        scope=f"{payload.scope.current_window} vs {payload.scope.previous_window}; {payload.scope.source_coverage}",
        executive_summary=payload.executive_summary,
        scorecard=scorecard,
        platform_lines=tuple(lines),
        data_quality=payload.data_quality,
        artifact_paths=artifact_paths,
        reconciled=reconciled,
        generated_at=payload.provenance.generated_at,
    )
