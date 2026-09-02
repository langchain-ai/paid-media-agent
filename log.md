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
