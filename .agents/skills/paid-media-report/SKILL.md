---
name: paid-media-report
description: Build a reconciled paid-media report or executive summary from deterministic analysis results and render it as a shareable artifact.
---

# Paid-media report

Use this skill when the user requests a report, recurring summary, PDF, or portfolio review.

1. Read `/skills/paid-media-wiki/reporting.md`.
2. Confirm scope, source coverage, window, comparison, timezone, and currency.
3. Generate or reuse a `compare_periods` analysis artifact id.
4. Call `render_report` with the analysis artifact id, a title, a short executive summary (change,
   business meaning, action, material caveat), and structured recommendations with evidence,
   expected effect, confidence, measurement, and reversal. Copy no raw rows into prose.
5. Code renders layout, tables, number formats, missing states, and provenance. Do not author HTML,
   CSS, tables, or page layout in model output.
6. The tool reconciles every rendered value against the analysis before writing files and returns
   a `report` summary plus file paths under `workspace/out/`. PDF is produced when WeasyPrint's native
   libraries are installed; otherwise the HTML file is the artifact and the result says so.
7. Deliver the artifact and the compact accessible summary. Name unavailable platforms and suppressed
   totals.

Never project, annualize, or convert currency unless the user requested it and deterministic code
performed the calculation.
