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

## 2026-09-02 (setup wizard redesign)

- Rebuilt the console as a guided wizard on the CORE 14 tokens with brand marks: welcome with
  capability visuals and example prompts, provider cards (eleven presets plus custom key names and
  base URLs), Pipeboard account picker with checkboxes, a "Try it" step (in-page question through
  the local graph, LangGraph Studio start/stop), and a recommended Managed Deep Agents path.
- Added `PAID_MEDIA_MODEL_API_KEY_ENV`, custom `*_API_KEY` names in the env allowlist, provider
  extras, `langgraph.json` with `paid_media_agent.runtime.graph:make_graph`, and the `ask` action.
- Console exports `.env` values into its process so provider SDKs and child processes see them,
  and clears values it exported when they are blanked; shell-provided values are never touched.
- Verified with headless Chromium: eleven provider cards, custom key flow, Studio serving the
  graph on port 2024, path choice, MDA preflight, dark theme; zero browser errors.
- No OpenAI key was available in this environment, so the welcome art is procedural (canvas glyph
  field and inline SVG); generated images can replace it under `admin/static/`.

## 2026-09-02 (generated onboarding art)

- Generated the welcome art with gpt-image-2 through the LangSmith LLM Gateway's direct OpenAI
  path (`gateway.smith.langchain.com/openai/v1`): two backgrounds (light and dark glyph fields
  that fade to a clear center) and three capability tiles, all in the CORE 14 palette with no text.
  Converted to WebP (18 KB backgrounds, 2 to 4 KB tiles) under `admin/static/art-*.webp`.
- Backgrounds switch with the theme in CSS; tiles are `<img>` elements with the inline SVG as an
  error fallback. The canvas glyph field is gone.
- The prompt pipeline lives outside the repository (it needs an image-capable key); assets are
  regenerated by re-running it and dropping the WebP files in place.

## 2026-09-02 (setup wizard: first-run pass)

- Reworked the local setup wizard as a developer first-run: fixture demo is the
  welcome primary, Anthropic is the featured model with the rest behind More
  providers, a green model test or account map advances automatically, and Done
  offers doctor / Advanced / back to the runtime path.
- Copy is one outcome sentence per step. Stepper title and path screen are both
  "Where it lives". Recommended on the managed card is a corner badge again so
  it cannot collide with the title. No Agent Chat UI; Try it stays a one-shot
  ask with a designed answer receipt.
- Visual system is still CORE 14. No extra ASCII chrome. Same localhost token,
  Host allowlist, CSP, and no secret echo.

## 2026-09-02 (setup console: engineering pass)

- Raised the console's reading scale for a technical audience: body 15/24, controls 40px, inputs
  14px, headings 26/34, and more room between fields, list rows, and blocks.
- Rewrote the wizard copy to say what the runtime is rather than what it feels like: a facts strip
  (deepagents + langgraph, pipeboard mcp, deny-by-default tools, hitl approvals), precise
  capability notes, and the equivalent shell command printed under each step.
- Removed noise: the welcome checklist that duplicated the progress chips, duplicate skip and
  continue actions, the redundant selection checkbox on the runtime cards, and finished process
  logs. A scrim keeps the generated background as texture rather than content.
- Fixed alignment by measuring rather than eyeballing: `grid-auto-rows: 1fr` equalizes provider
  cards across rows (were 124/96/116px, now uniform), a minimum note height aligns the runtime
  cards' bullet lists, and the Recommended badge became an inline lead-in so it cannot overlap a
  card title.

## 2026-09-03 (parity audit against the reference agent)

- Inventoried the reference (tools, skills, wiki, middleware, surfaces, reports, evals, fixtures,
  instructed behaviors) read-only and mapped it against this repository in
  `docs/audits/parity-audit-2026-09-03.md`.
- Ran fifteen business questions through the local LangGraph Server on the synthetic fixtures and
  graded them against deterministic ground truth computed from the same fixtures.
- Found and fixed: two 33-minute gateway stalls (no per-request model timeout), a `read_file`
  result over the offload budget turning into a second artifact (paged tools are now exempt and
  artifacts are pretty-printed), no deterministic way to answer pacing or anomaly questions
  (`summarize_window`), inconsistent "last week" resolution across answers (window convention in
  the skill and wiki), no model-call ceiling per run, and sandboxes created with open egress.

## 2026-09-02 (sandbox parity)

- Answered "do we need a local Docker container" with the reference's own model: no. MDA's
  sandbox is a remote LangSmith container and `mda dev` uses the same one as production; the
  reference's parity gate is the production graph plus the managed sandbox, with the host
  backend as a dev loop.
- Added `runtime/sandbox.py` (`build_backend`, `Sandbox`, `WorkspaceMirror`, `SandboxPdfEngine`,
  `probe_sandbox`) and threaded a `Backend` through profiles, assembly, and the local, LangGraph
  Server, and self-hosted runtimes. `execute` stays hidden from the model; only host code uses
  the sandbox shell.
- MDA evaluates `sandbox/__init__.py` with `ast.literal_eval`, so environment-driven arguments
  are rejected; `sandbox publish|use` generate the literal declaration and `.env` together.
- Unit tests cover mount paths, artifact mirroring, in-sandbox PDF rendering, and the probe with
  an in-memory backend; `tests/integration/test_live_sandbox.py` runs the probe for real when
  `PAID_MEDIA_LIVE_TESTS=1` and a snapshot are set.
- Live run with the reference project's sandbox-capable key: `sandbox publish` built
  `paid-media-agent-sandbox-v2` on LangSmith (id `276702e7-...`), `sandbox test` passed all
  seven checks in 23 s, LangGraph Server in sandbox mode answered `ls /skills` from the sandbox
  and rendered a report whose PDF was produced inside the sandbox (this Mac has no Pango), the
  model listed the mirrored `/workspace` artifacts, `mda build` accepted the generated
  declaration, and `mda dev` provisioned a per-thread sandbox from the same snapshot with skills,
  wiki, and instructions mounted.
- Fixes found by that run: the SDK's `create_snapshot_from_dockerfile` uses its `timeout`
  argument (default 60 s) as the build command timeout and a 10 s HTTP timeout for the capture
  call, so both are raised; Dockerfile-built snapshots resolve by id, not by `name:latest`, so
  the id is pinned in `.env` and in the MDA declaration; the sandbox shell ignores image `PATH`,
  so WeasyPrint is installed into the system Python; Deep Agents rejects path permissions on a
  backend that can execute, so path rules apply only to the repository backend; artifact writes
  inside async tools run in a worker thread to satisfy the dev server's blocking-call guard; and
  sandboxes are created with `delete_after_stop_seconds` because a killed server never runs its
  exit handler.
- One LangSmith key had gateway access without sandbox permissions and another the reverse;
  `LANGSMITH_GATEWAY_API_KEY` plus `PAID_MEDIA_MODEL_API_KEY_ENV` covers that split.

## 2026-09-02 (sandbox end-to-end as a new developer)

- Ran the whole path in a fresh copy with the LangSmith Gateway key: `uv sync`, `demo`,
  `doctor`, `report`, `config set`, `test model`, `ask`, `mda check`, `mda build`, `langgraph dev`
  + SDK thread, `mda dev` + SDK thread, `serve` + authenticated API call, and the setup console.
- `mda dev` failed to load the graph because the managed build installs core dependencies only
  and `langchain-openai` (the gateway client) was an extra; both common provider packages now
  ship in core.
- `langgraph dev` failed on the first run: the graph factory called `asyncio.run` inside the
  server's loop and then hit the blocking-call guard. The factory is async and builds in a
  worker thread, cached per process.
- `serve` could not build the gateway model because the CLI never exported `.env`; the CLI group
  now applies `.env` before every command. `serve` also gained `--host/--port`.
- The API returned the Python repr of content blocks and the model guessed "last week" as a 2025
  window; fixed with text flattening in the surface runner and a middleware that appends the
  current UTC date to the system message per call. Fixture reads now state their data window.
- The console's Direct platforms route had not landed; it exists now, and the model step derives
  readiness from the computed key flag so a gateway key counts.
- `mda deploy` returned `403 deployments:read`: the key used lacks deployment permissions. Hosted
  deployment stays unverified until a key with that permission is available.

## 2026-09-02 (platform parity and reports)

- Confirmed from Pipeboard's public integrations page that LinkedIn and X are not Pipeboard
  connectors; added direct adapters under `tools/direct/` for LinkedIn Ads, X Ads, and OpenAI Ads
  with request-shape tests against mocked transports. They contribute read tools to the same
  deny-by-default catalog and never define mutations.
- Verified that the installed LangChain routes `langsmith:provider/model` through the LLM Gateway
  (a 2.9 s live call), while `LANGSMITH_GATEWAY=true` did not reroute ChatAnthropic in this build;
  the console's recommended preset therefore uses the `langsmith:` form and the registry treats
  gateway models as portable-selector models.
- Added `paid-media-agent report --cadence weekly|monthly` and MDA schedules so the scheduled
  cross-platform report runs deterministically, and a Direct platforms route in the console.

## 2026-09-02 (setup wizard: Budget Card layout)

- Restyled the local setup wizard to the Watermelon Budget Card composition while keeping CORE 14
  tokens: L-corner ticks, a large display title, a hairline step meter, a spent/remaining-style
  metric pair, and a three-segment capability breakdown. No Agent Chat UI. Secrets still stay in
  `.env` and password fields.

## 2026-09-02 (setup wizard: restore original paper design)

- Reverted the Budget Card restyle. The setup console is back to the paper card, chip stepper,
  capability art tiles, and rounded controls. No Agent Chat UI. Same localhost token, Host
  allowlist, CSP, and no secret echo.
