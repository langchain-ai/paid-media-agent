# Repository log

Append material architecture, source, and operating-contract changes here. Do not rewrite earlier
entries except to correct a factual typo with an explicit correction entry.

## 2026-09-01

- Established the spec-first local repository.
- Defined one portable Deep Agents core with MDA and self-hosted adapters.
- Made deny-by-default tool authorization, deterministic computation, and digest-bound approval the
  core execution contracts.
- Added a public paid-media wiki plan, source inventory, phased implementation contract, and a Claude
  Fable 5.1 execution prompt.

## 2026-09-01 (implementation)

- Implemented the `src/paid_media_agent` package with one shared `build_agent_components` assembly,
  a `paid-media-agent` console script, and a normal `uv_build` package (replaced `tool.uv.package = false`).
- Added deny-by-default catalog classification, host-side read dispatch with JSON-schema validation
  and alias-only account scope, the exact-match model capability registry, provider-native and
  portable selection paths, an invocation guard, result offload, and redaction.
- Added deterministic period comparison with reconciliation, versioned report payloads, Jinja2/WeasyPrint
  rendering with HTML fallback, and an artifact bridge.
- Added governed writes: `ChangeSet`, host-signed single-use `ApprovalClaim`, `WriteReceipt`, state
  machine, in-memory and Postgres repositories, a fake write provider, one-attempt execution, and
  bounded readback through the authorized read path.
- Added the MDA entry, native Slack declaration, rich Slack service with Socket Mode and signed HTTP
  transports, a FastAPI boundary, UI views, and the self-hosted runtime.
- Decided against `connectors/mcp.py`: MDA's MCP connector binds provider tools directly to the
  model, which the authorization contract forbids. Recorded in `open-questions.md`.
- Added `pydantic-settings`, `click`, and `jsonschema` as explicit dependencies (LangChain does not
  validate dict-form tool schemas).

## 2026-09-01 (slice 6: live-write readiness, writes still off)

- Made the reviewed mutation set data (`config/write-policy.example.toml`) validated against the
  current catalog; rows that fail validation are excluded and reported by `doctor`.
- Bound the mutation schema hash and policy-row digest into the proposal digest; execution rejects
  `stale_catalog` and `stale_policy`.
- Added code-derived risk flags to proposals, a pre-interrupt guard so only real proposals on the
  current thread pause for review, provider validate-only support, honest
  `provider_acknowledged` receipts, and `discover_write_operations`.
- Added `WriteGate` with an incident kill-switch file, the global flag, a pinned reviewed catalog
  revision, and a canary tool allowlist; added the exact `PipeboardWriteProvider`; live profiles no
  longer use the fake when the catalog is live.
- Wrote `docs/operations/live-write-runbook.md`. No live canary ran; that still needs separate
  human authorization and the gate settings above.
- Review against the private reference implementation drove these changes: honest mutation vs
  verification outcomes, edit-as-new-authorization, static approver policy, exclusion before
  review, contract identity beyond the payload digest, and Slack 429 retries.

## 2026-09-01 (slice 7: release hardening)

- Added `LICENSE` (Apache-2.0 as the recommended default pending maintainer approval),
  `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, project metadata and URLs.
- Added CI (`.github/workflows/ci.yml`: lint, format, types, offline tests, fixture demo, MDA
  import smoke, secret scan on Python 3.11 and 3.13), a weekly compatibility workflow that tests an
  upgraded lock without committing, and Dependabot for the uv and Actions ecosystems.
- Added `examples/ask.py`, `docs/migration.md`, `sandbox/README.md`, a Slack app manifest example,
  and README sections for writes, the MDA path, and release status.
- Screenshots are not included: no Slack workspace or model run was available in this session.

## 2026-09-02 (setup console)

- Added `src/paid_media_agent/admin/`: shared host actions, allowlisted `.env` editor, account
  alias editor, fixed-template process manager, onboarding routes, and a localhost FastAPI console
  with a per-run token, Host check, CSP, and no secret echo.
- Added CLI groups `config`, `accounts`, `catalog`, `policy`, `test`, `mda`, `writes`, and
  `setup`; every action has `--json`.
- Verified the page end to end with headless Chromium: demo, model form, account discovery and
  mapping, policy validation, kill switch, MDA preflight, process controls, dark theme; zero
  browser errors. Screenshots under `docs/screenshots/`.
- Moved `fastapi` and `uvicorn` into core dependencies because the console is the first command a
  developer runs.
