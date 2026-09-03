# Changelog

## Unreleased (2026-09-01)

### Added (sandbox parity)

- `PAID_MEDIA_BACKEND=sandbox`: the model's filesystem in a LangSmith sandbox built from
  `sandbox/Dockerfile`, with skills and the wiki at the repository's paths, host artifacts
  mirrored under `/workspace`, and PDF reports rendered inside the sandbox.
- `paid-media-agent sandbox publish|use|test` and a console route for building, declaring, and
  probing the snapshot; `mda check` verifies the MDA declaration matches `.env`.

### Added (parity audit follow-ups)

- `summarize_window`: deterministic single-window summary (per-entity spend share, CPA, ROAS,
  CTR, pacing against `list_campaigns` budgets, daily series with flagged days) so pacing,
  anomaly, and top-N questions never need arithmetic in prose.
- Per-request model timeout (`PAID_MEDIA_MODEL_TIMEOUT_SECONDS`) enforced by middleware as well
  as the SDK, SDK retries, and a per-run model-call limit (`PAID_MEDIA_MAX_MODEL_CALLS`).
- Sandboxes are created with default-deny egress; only loopback is allowed.
- The analysis skill and wiki define how relative windows resolve (Monday to Sunday weeks,
  "last N days" anchored on the platform's complete date, calendar months).

### Fixed

- Filesystem tool output is no longer offloaded: a `read_file` over the budget became an artifact
  about an artifact. Artifacts are written one field per line so `read_file` can page them.

- The LangGraph Server graph factory is now async and builds off the event loop; it previously
  called `asyncio.run` and tripped the server's blocking-call guard on the first run.
- Every CLI command exports the project `.env` into its process before running, so `serve`
  and `slack` find provider keys the same way `langgraph dev` and the managed build do.
- The self-hosted API returned the Python repr of content blocks; it now returns the text.
- The model is told the current UTC date on every call, so "last week" resolves from today.
- Fixture performance reads report the static data window so an empty range is explained.
- `serve` accepts `--host` and `--port`; the Anthropic and OpenAI integration packages moved
  into core dependencies so managed builds can run the recommended gateway preset.

### Added

- Direct read adapters for LinkedIn Ads (OAuth 2.0 with refresh), X Ads (OAuth 1.0a), and OpenAI
  Ads, joined into the same authorized catalog as Pipeboard tools.
- LangSmith LLM Gateway as the recommended model preset (`langsmith:provider/model`).
- Deterministic weekly and monthly report command plus MDA schedules.

- Local setup console (`paid-media-agent setup`): a guided onboarding wizard (welcome with
  capabilities, model providers with custom key names, Pipeboard accounts with checkboxes, try it
  with an in-page question and LangGraph Studio, managed vs self-hosted path) plus an advanced view
  over the same host actions as the CLI (`config`, `accounts`, `catalog`, `policy`, `test`, `mda`,
  `writes`).
- Setup wizard tuned for engineers: larger reading scale, the runtime facts it actually runs on,
  and the equivalent shell command under every step.
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
