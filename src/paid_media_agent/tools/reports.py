"""Model-facing `render_report` tool. Narrative in, reconciled artifact out."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field, ValidationError

from paid_media_agent.domain.analysis import PeriodComparison
from paid_media_agent.domain.reports import NARRATIVE_MAX, Recommendation
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.reports.bridge import ArtifactBridge, BridgeError
from paid_media_agent.reports.render import (
    PdfEngine,
    ReportRenderer,
    build_report_payload,
    reconcile_report,
    report_summary,
)
from paid_media_agent.tools.artifacts import ArtifactError, ArtifactStore

RENDER_REPORT_TOOL = "render_report"


class RenderReportArgs(BaseModel):
    analysis_artifact_id: str = Field(description="Analysis artifact id from compare_periods.")
    title: str = Field(max_length=160)
    executive_summary: str = Field(
        max_length=NARRATIVE_MAX, description="Short narrative: change, meaning, action, caveat."
    )
    recommendations: list[Recommendation] = Field(default_factory=list)


def run_render_report(
    artifacts: ArtifactStore, args: RenderReportArgs, *, pdf_engine: PdfEngine | None = None
) -> dict[str, Any]:
    record = artifacts.read(args.analysis_artifact_id)
    if record.metadata.kind != "analysis":
        raise ArtifactError("artifact is not an analysis artifact")
    comparison = PeriodComparison.model_validate(record.payload)
    payload = build_report_payload(
        comparison,
        analysis_artifact_id=args.analysis_artifact_id,
        title=args.title,
        executive_summary=args.executive_summary,
        recommendations=tuple(args.recommendations),
    )
    problems = reconcile_report(payload, comparison)
    if problems:
        raise ArtifactError("report reconciliation failed: " + "; ".join(problems))
    out_dir = artifacts.root / "out"
    renderer = ReportRenderer(out_dir, pdf_engine=pdf_engine)
    rendered = renderer.render(payload)
    bridge = ArtifactBridge(out_dir)
    receipts = [bridge.validate(rendered.html_path)]
    artifacts.publish(rendered.html_path)
    if rendered.pdf_path is not None:
        receipts.append(bridge.validate(rendered.pdf_path))
        artifacts.publish(rendered.pdf_path)
    payload_meta = artifacts.write_json(
        "report",
        payload.model_dump(mode="json"),
        schema_version=payload.schema_version,
        tool_name=RENDER_REPORT_TOOL,
    )
    summary = report_summary(
        payload, artifact_paths=tuple(r.path for r in receipts), reconciled=True
    )
    return {
        "report": summary.model_dump(mode="json"),
        "payload_artifact_id": payload_meta.artifact_id,
        "files": [r.model_dump(mode="json") for r in receipts],
        "pdf": "rendered"
        if rendered.pdf_path is not None
        else f"unavailable: {rendered.pdf_error}",
    }


def build_render_report_tool(
    artifacts: ArtifactStore, *, pdf_engine: PdfEngine | None = None
) -> BaseTool:
    def _run(**kwargs: Any) -> str:
        try:
            args = RenderReportArgs.model_validate(kwargs)
            return json.dumps(run_render_report(artifacts, args, pdf_engine=pdf_engine))
        except (ArtifactError, BridgeError, ValidationError, ValueError) as exc:
            return json.dumps({"error": True, "detail": sanitize_exception(exc)})

    return StructuredTool(
        name=RENDER_REPORT_TOOL,
        description=(
            "Render a reconciled report (HTML, and PDF when available) from an analysis artifact. "
            "You supply the title, a short executive summary, and structured recommendations; code owns layout and numbers."
        ),
        args_schema=RenderReportArgs,
        func=_run,
    )
