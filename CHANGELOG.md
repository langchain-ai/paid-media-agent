# Changelog

## Unreleased

### Added (onboarding inside coding agents)

- `paid-media-agent setup --no-token` serves the console at a plain URL for hosts whose browser
  pane cannot carry the per-run token; it accepts same-origin calls only. `.claude/launch.json`
  (`setup`) opens it in Claude Code desktop's Browser pane, `.cursor/rules/onboarding.mdc` steers
  Cursor's built-in browser, and `AGENTS.md` carries the host-neutral instruction (Codex app
  included).

### Changed (two deployment paths, MDA recommended)

- Self-hosting is back on `main` next to Managed Deep Agents: `paid-media-agent serve` (FastAPI
  boundary with bearer tokens), Postgres persistence, the rich Slack adapter over Socket Mode or
  signed HTTP, `Dockerfile` and `docker-compose.yml`, `test slack|db`, and the console's "Where
  it lives" step with two cards (Managed Deep Agents recommended, Self-host second). The
  self-hosted runtime now builds on the same configured profile as `agent.py` and the CLI.
  The per-process sandbox backend and the LangGraph Server factory did not return; `mda dev` is
  the local server, and the self-hosted model reads the repository directly.

### Changed (Managed Deep Agents only, 2026-09-08)

- `main` deploys with Managed Deep Agents and nothing else. The self-hosted API, Postgres
  persistence, the rich Slack transports (Socket Mode, signed HTTP), the local LangGraph Server
  and Studio factory, `PAID_MEDIA_BACKEND`, `PAID_MEDIA_RUNTIME`, and the Docker files moved to
  the `self-hosted` branch (frozen at `a5477d9`); `docs/self-hosting.md` explains why and how to
  use it. The Block Kit renderers, the transport-neutral Slack service, and the runner stay for a
  custom Slack channel.
- The business wiki is now the skill `skills/paid-media-wiki/` (was `docs/business-context/`),
  because MDA syncs `skills/` into the deployment and nothing else from the repository: in the
  hosted sandbox `/docs/business-context` did not exist.
- New `get_org_context` tool returns the organization profile and shared briefs to the model, so
  the same context is available locally and inside the per-thread sandbox; skills and
  `instructions.md` call it instead of reading `/docs/org` files.
- `paid-media-agent ask`, `report`, and the console's "Try it" compile the deployment's profile
  (live catalog when credentials exist) instead of a fixture-only runtime.
- Console: the wizard is Model, Ad accounts, Your business, Try it, Deploy, Done; the Deploy step
  collects the approver identities next to the LangSmith key. Jinja2 moved into core so the
  scheduled reports render in the managed build. Extras `slack`, `self-host`, and `studio` are
  gone.

### Added (organization onboarding)

- `docs/org/`: the organization's own context (business, conversion that counts, targets, budget,
  markets, seasonality, naming, approvers, shared links and files), ignored by git and mounted at
  `/docs/org` in every runtime. Filled from the console step "Your business", from
  `paid-media-agent org interview|set|add-link|add-file`, or by the agent through the
  `paid-media-org-onboarding` skill and the `update_org_profile` and `add_org_source` tools. The
  analysis skill reads it before generic doctrine.

### Added (release readiness)

- Repository health files and automation: `CODE_OF_CONDUCT.md`, issue and pull request templates,
  `.pre-commit-config.yaml`, a tag-driven release workflow, Dependabot, `Makefile` shortcuts, and
  `docs/open-source-principles.md` with the rules this repository holds itself to.
- Self-hosting in one command: `Dockerfile` (with the PDF native libraries) and
  `docker-compose.yml` with Postgres.
- Synthetic data anchored to today (`PAID_MEDIA_FIXTURE_ANCHOR` pins a date), so sample prompts
  such as "last week" keep working on any day the repository is cloned.

### Fixed (console walkthrough)

- Console commands now show `uv run ...` exactly as a fresh checkout runs them.
- Answers in the Try-it step render as formatted text and tables instead of raw markdown.
- The provider grid highlights the LangSmith Gateway card for `langsmith:` models instead of
  "Custom"; the accounts step points to the direct platforms; the runtime step title matches its
  chip; the preflight shows the sandbox snapshot; the Done step lists what to do next.
- The MDA import smoke test no longer depends on the developer's local `.env`.

### Verified

- Managed deployment end to end: `mda deploy` built the sandbox recipe, deployed, answered a
  run through the LangGraph SDK in 32 s, and registered the weekly and monthly schedules. Slack
  provisioning needs a one-time OAuth grant by the workspace owner.

### Added (sandbox parity)

- `PAID_MEDIA_BACKEND=sandbox`: the model's filesystem in a LangSmith sandbox built from
  `sandbox/Dockerfile`, with skills and the wiki at the repository's paths, host artifacts
  mirrored under `/workspace`, and PDF reports rendered inside the sandbox.
- `paid-media-agent sandbox publish|use|test` and a console route for building, declaring, and
  probing the snapshot; `mda check` verifies the MDA declaration matches `.env`.

### Added (gap closure)

- Ad-group grain on the fixture catalog (`get_ad_group_performance`, derived deterministically from
  campaign rows) and on the direct adapters: LinkedIn creatives, X line items, OpenAI Ads ad
  groups. Normalization keys rows by the requested grain and reads carry the grain forward.
- Five public playbook wiki pages (benchmarks, anomalies and significance, bidding and budget,
  platform playbooks, answer style) routed from the analysis skill.
- `tests/eval/`: the fifteen-question eval with a runner and a grader over fixture ground truth.
- The signed Slack HTTP transport is served by `serve` when `SLACK_TRANSPORT=http`, and a thread
  reply of the form `edit <field> <value>` edits the waiting proposal.

### Changed (clarity pass)

- Removed dead code and duplicated helpers (one `project_root`, one text flattener, one account
  schema builder, one `_NoArgs`); `admin/model_presets.py`, `tools/write_policy.py`, and
  `tools/write_tools.py` split out of the two largest modules; `tools/analysis.py` is now
  `tools/compare_periods.py`; the demo runner lives in `testing/demo_script.py`.
- Dropped the catalog TTL setting (the catalog loads once per process), the unused schedule run
  mode, the `LANGSMITH_GATEWAY` env key, and the Slack Cancel action.
- `OPERATIONS.md` is the command reference; the README quick start leads with the credential-free
  demo; `AGENTS.md` maps the whole tree; build scaffolding moved to `docs/history/`.
- Inert `noqa` markers removed and `RUF100` enabled so unused suppressions fail lint.

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
