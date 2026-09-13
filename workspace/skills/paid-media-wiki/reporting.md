# Reporting

A paid-media report is a decision artifact, not a dashboard dump.

## Required structure

1. Scope: accounts, platforms, window, comparison, currency, and source coverage.
2. Executive summary: what changed, why it matters, and the most important next action.
3. Reconciled scorecard: spend, delivery, conversion, and business outcomes with definitions.
4. Platform sections: material drivers, not every row.
5. Recommendations: evidence, expected effect, confidence, measurement, and reversal.
6. Data quality: missing sources, incomplete windows, attribution differences, and suppressed totals.
7. Provenance: source artifacts, generated time, analysis version, and report schema version.

## Rendering

The model may write bounded narrative fields. Code renders layout, tables, labels, number formats,
footnotes, missing states, page breaks, and files. Slack, PDF, and UI derive from one `ReportPayload`.

## Partial completion

If one platform fails, keep healthy platform sections and label the failure. Suppress a portfolio total
that would imply full coverage. Do not replace unavailable platforms with zero rows.

## Recommendation amounts

Any spend, budget, savings, or reallocation amount must trace to current structured data and policy.
Do not extrapolate a weekly amount into a monthly claim unless the projection is explicitly requested,
labeled, and computed by code.

