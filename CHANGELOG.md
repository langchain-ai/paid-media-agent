# Changelog

## Unreleased (2026-09-01)

### Added

- Local setup console (`paid-media-agent setup`): a guided onboarding wizard (welcome with
  capabilities, model providers with custom key names, Pipeboard accounts with checkboxes, try it
  with an in-page question and LangGraph Studio, managed vs self-hosted path) plus an advanced view
  over the same host actions as the CLI (`config`, `accounts`, `catalog`, `policy`, `test`, `mda`,
  `writes`).
- Generated onboarding art (gpt-image-2): light and dark glyph-field backgrounds and three
  capability tiles, shipped as small WebP files with inline SVG fallbacks.
- `langgraph.json` and a graph factory for LangGraph Server and Studio; `studio` extra.
- Provider extras for Groq, xAI, Mistral, and DeepSeek; OpenAI-compatible presets (OpenRouter,
  Moonshot, Zhipu) through `PAID_MEDIA_MODEL_BASE_URL` and `PAID_MEDIA_MODEL_API_KEY_ENV`.

- Shared Deep Agents assembly with a fixture-backed offline demo (`paid-media-agent demo`).
- Deny-by-default authorized catalog, host-side read dispatch with schema validation and
  alias-only account scope, provider-native and portable tool selection, invocation guard, result
  offload, and redaction.
- Deterministic period comparison, versioned report payloads with HTML and optional PDF rendering,
  reconciliation, and an artifact bridge.
- Governed writes: typed proposals, host-signed single-use approvals, one mutation attempt,
  bounded readback, honest receipts, risk flags, contract identity (schema and policy digests).
- Live-write readiness: reviewed policy file, `WriteGate` (kill switch, global flag, pinned
  catalog revision, canary allowlist), exact Pipeboard write adapter, operator runbook.
- MDA entry with native Slack, rich Slack adapter (Socket Mode and signed HTTP), FastAPI boundary,
  UI views, self-hosted runtime with Postgres persistence.

### Not released

- Live provider mutations. The gates stay closed until a separately authorized canary.
