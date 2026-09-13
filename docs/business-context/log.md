# Business-context log

## 2026-09-01

- Created a public, company-neutral paid-media doctrine.
- Defined goal hierarchy, metric and attribution boundaries, decision workflow, reporting contract,
  and governed-write safety.
- Established live schemas and official provider docs as higher authority than compiled context.

## 2026-09-01 (implementation)

- Encoded the metric definitions, missing-is-not-zero rule, equal-length comparison windows, and
  cross-platform total suppression in `tools/compute.py`; the fixture demonstrates a platform with
  no conversion value and an incomplete window.
- Reports render from `ReportPayload` with per-platform attribution caveats and visible unavailable sources.

## 2026-09-12: Pipeboard coverage and sample isolation

All eight Pipeboard catalogs load concurrently with bounded timeouts. LinkedIn is owned by
Pipeboard when its token is configured. Unknown spend mappings remain raw provider artifacts.
Explicit sample sessions use only fixture tools and accounts; live sessions add no fixtures.
