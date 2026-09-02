# Operations

## Local prerequisites

- Python 3.11 or newer
- `uv`
- a tool-calling model provider key for live model runs
- Docker only for snapshot and production-parity checks
- a Pipeboard token only for live platform reads
- Slack bot and app tokens only for the rich Slack adapter

Start with fixtures. Live credentials are never required to run the default test suite.

## Setup

```bash
cp .env.example .env
uv sync --all-extras --dev
```

Keep `.env` local. Do not place secrets in TOML, YAML, fixtures, example commands, screenshots, or
trace exports.

## Runtime commands

Every `paid-media-agent` command exports the allowlisted values of the project `.env` into its
own process first, so provider SDKs that read their key from the environment work without a
manual `export`. Values already set in your shell win over the file. `serve` takes `--host` and
`--port` (defaults `PAID_MEDIA_API_HOST` / `PAID_MEDIA_API_PORT`); the bearer a client sends is
the part of `PAID_MEDIA_API_TOKENS` before `:caller`.

The implementation must expose these stable commands:

```bash
uv run paid-media-agent demo
uv run paid-media-agent doctor
uv run paid-media-agent serve
mda dev
```

`doctor` checks configuration shape, provider package availability, Pipeboard configuration, account
alias resolution, write disablement, Slack transport configuration, report rendering, and
persistence without printing secret values. `doctor --snapshot` runs the sandbox compatibility
contract from [docs/architecture/sandbox-and-snapshots.md](docs/architecture/sandbox-and-snapshots.md).

Optional native dependencies:

- PDF reports use WeasyPrint, which needs Pango and Cairo system libraries (`brew install pango` on
  macOS, `libpango-1.0-0 libcairo2` on Debian). Without them reports render as HTML only and
  `doctor` reports `report_pdf` as a warning. `sandbox/Dockerfile` bakes them into the snapshot.
- The self-hosted API needs the `self-host` extra and `PAID_MEDIA_API_TOKENS` (`token:caller,...`).
  Durable state needs `DATABASE_URL`; without it the profile keeps state in memory.

## Live checks

The default test suite is offline. Live, read-only checks are opt-in:

```bash
PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q
```

They require `PIPEBOARD_API_TOKEN` for the catalog check and `DATABASE_URL` for the Postgres
round-trip. They never call a provider mutation.

## Source refresh

Before changing a claim about Deep Agents, MDA, model support, provider tool search, Slack, or
Pipeboard, refresh the relevant official source in [docs/sources/official-links.md](docs/sources/official-links.md).
Before changing paid-media doctrine, update [docs/business-context/sources.md](docs/business-context/sources.md).

Source order:

1. live provider schema and runtime evidence for current capability;
2. official vendor documentation for contracts;
3. deterministic fixtures and tests for repository behavior;
4. compiled wiki pages for stable doctrine;
5. model memory or prose only as a lead to verify.

## Release gates

- license and trademarks approved;
- clean install from a new checkout;
- fixture demo works without external accounts;
- model matrix passes the tool-selection contract;
- read path has no mutation reachability;
- write path rejects missing, stale, edited, foreign-user, foreign-account, and digest-mismatched
  approvals;
- no automated test can reach a live mutation;
- reports reconcile to their structured inputs;
- MDA and self-hosted profile smokes use the same agent assembly;
- Socket Mode and signed HTTP Slack paths render the same presentation objects;
- logs, errors, traces, and generated artifacts pass secret and private-data scans;
- documentation links and commands are valid.

Publishing, deployment, migrations, account connection, and live write canaries require explicit
human authorization.

## Write gates

Every execution passes `WriteGate` in `tools/writes.py`. The fixture fake needs only a clear kill
switch. A live provider additionally needs `PAID_MEDIA_WRITES_ENABLED=true`,
`PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION` equal to the current catalog revision, and the tool name in
`PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS`. The reviewed mutation set is the TOML file at
`PAID_MEDIA_WRITE_POLICY_PATH`; `doctor` reports rows that fail validation. Incident procedure and
canary steps: [docs/operations/live-write-runbook.md](docs/operations/live-write-runbook.md).

## Setup console

`uv run paid-media-agent setup [--port 8765] [--no-open]` serves `src/paid_media_agent/admin/` on
127.0.0.1 with a per-run admin token in the URL fragment. Every page action calls the same
functions as the CLI subcommands (`admin/actions.py`), so agents can script the same steps with
`--json`. The console writes `.env` and `config/accounts.toml` locally, starts fixed-template
processes (`serve`, `slack`, `mda dev`, `mda deploy` with confirmation) with logs under
`workspace/logs/`, and exposes the kill switch. It is not a hosted admin panel: do not expose the
port, and prefer deployment secrets over `.env` for MDA and self-hosted production.

## Local LangGraph Server and Studio

`langgraph.json` points LangGraph Server at `paid_media_agent.runtime.graph:make_graph`, which
builds the shared assembly with the configured model and the fixture or live catalog and compiles
it without a checkpointer (the server owns persistence). Install the `studio` extra, then:

```bash
uv run langgraph dev            # http://127.0.0.1:2024, opens Studio
```

The setup page's "Try it" step starts and stops the same server and links to Studio. `mda dev`
is the managed equivalent for the MDA path. Neither needs a Pipeboard token: without one the
fixture accounts are used.

## Model providers

`PAID_MEDIA_MODEL` takes `provider:model`. Native provider packages ship as extras (`anthropic`,
`openai`, `google`, `groq`, `xai`, `mistral`, `deepseek`). OpenAI-compatible endpoints (OpenRouter,
Moonshot, Zhipu, your own gateway) use the `openai:` prefix, `PAID_MEDIA_MODEL_BASE_URL`, and a key
stored under any `*_API_KEY` name declared in `PAID_MEDIA_MODEL_API_KEY_ENV`. A base URL disables
provider-native tool search; the portable selector is used instead.

## Direct platforms

The setup console lists these under Advanced · Direct platforms (route `direct`): one form per
platform, then the same account discovery as Pipeboard. `paid-media-agent accounts discover`
lists direct accounts next to Pipeboard ones once their credentials are in `.env`.

LinkedIn Ads, X Ads, and OpenAI Ads are not Pipeboard connectors. Set their credentials in `.env`
(see `.env.example`); the runtime adds their read tools to the catalog on startup and
`paid-media-agent accounts discover` lists their accounts next to Pipeboard's. Token refresh for
LinkedIn happens in-process from `LINKEDIN_REFRESH_TOKEN`; X requests are signed with OAuth 1.0a.

## Scheduled reports

`paid-media-agent report --cadence weekly|monthly [--end YYYY-MM-DD] [--alias a]` runs the
deterministic pipeline. On MDA, `schedules/weekly_report.py` and `schedules/monthly_report.py`
start the agent in schedule mode with read and render tools only.
