# Operations

## Prerequisites

- Python 3.11 or newer and `uv`
- a tool-calling model key for live model runs (the fixture demo needs none)
- a Pipeboard token only for live platform reads; direct-platform credentials only for LinkedIn,
  X, and OpenAI Ads
- Slack bot and app tokens only for the rich Slack adapter

Start with fixtures. Live credentials are never required for the default test suite.

## Setup

```bash
uv sync --all-extras --dev      # `uv sync` alone is enough for the fixture demo
uv run paid-media-agent setup   # or edit .env by hand; the console seeds it from .env.example
```

Keep `.env` local. Do not place secrets in TOML, YAML, fixtures, example commands, screenshots, or
trace exports.

## Command reference

Every `paid-media-agent` command exports the allowlisted values of the project `.env` into its own
process first, so provider SDKs that read their key from the environment work without a manual
`export`. Values already set in your shell win over the file. Every command has `--json` where a
machine reads it, and the setup console runs the same actions.

| Command | What it does |
|---|---|
| `uv run paid-media-agent setup [--port] [--no-open]` | Local onboarding console over the actions below |
| `uv run paid-media-agent demo [--with-proposal]` | Fixture run through the real graph, optionally with a governed write |
| `uv run paid-media-agent doctor [--snapshot]` | Configuration, packages, catalog, Slack, PDF, persistence checks; `--snapshot` runs the sandbox contract |
| `uv run paid-media-agent config show\|set KEY=VALUE\|generate KEY` | Read or change `.env` without printing secrets; generate signing keys and API tokens |
| `uv run paid-media-agent test model\|pipeboard\|slack\|db\|all` | Connection tests that never print secret values |
| `uv run paid-media-agent accounts discover\|list\|add\|remove` | Host-side account discovery and alias mapping (six platforms) |
| `uv run paid-media-agent catalog show [--live]` | The authorized tool catalog: reads, admitted mutations, denied tools |
| `uv run paid-media-agent policy validate [--live]` | Validate the write policy against the fixture or live catalog |
| `uv run paid-media-agent ask "question"` | One question through the local runtime with the configured model |
| `uv run paid-media-agent report --cadence weekly\|monthly [--end DATE]` | Deterministic cross-platform report, HTML and PDF |
| `uv run paid-media-agent serve [--host] [--port]` | Self-hosted API; mounts the signed Slack HTTP transport when `SLACK_TRANSPORT=http` |
| `uv run paid-media-agent slack` | Rich Slack adapter in Socket Mode |
| `uv run paid-media-agent mda check\|dev\|deploy [--yes]` | Managed Deep Agents preflight, local managed run, hosted deploy |
| `uv run paid-media-agent sandbox publish\|use\|test` | Build, declare, and probe the LangSmith sandbox snapshot |
| `uv run paid-media-agent writes kill-switch on\|off` | Incident switch for live writes |
| `uv run langgraph dev` | LangGraph Server and Studio for the same graph (needs the `studio` extra) |

`serve` reads `PAID_MEDIA_API_HOST` and `PAID_MEDIA_API_PORT` by default; the bearer a client sends
is the part of `PAID_MEDIA_API_TOKENS` before `:caller`.

Optional native dependencies:

- PDF reports use WeasyPrint, which needs Pango and Cairo system libraries (`brew install pango` on
  macOS, `libpango-1.0-0 libcairo2` on Debian). Without them reports render as HTML only and
  `doctor` reports `report_pdf` as a warning; with `PAID_MEDIA_BACKEND=sandbox` the PDF renders
  inside the sandbox instead.
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

## Sandbox

`PAID_MEDIA_BACKEND` decides where the model's files live. `local` (default) roots the model at
the repository. `sandbox` opens one LangSmith sandbox per process from the snapshot named by
`PAID_MEDIA_SANDBOX_SNAPSHOT`: skills and the business wiki are uploaded at the same absolute
paths (`/skills`, `/docs/business-context`), every artifact host tools write is mirrored under
`/workspace`, and PDF reports render inside the sandbox, where the native libraries are baked
in. The model never gets a shell in either mode.

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # LangSmith builds sandbox/Dockerfile
uv run paid-media-agent sandbox test --json                              # open, probe, delete
uv run paid-media-agent config set PAID_MEDIA_BACKEND=sandbox
uv run langgraph dev                                                      # now runs against the sandbox
```

`publish` (or `sandbox use <name>` for an existing snapshot) writes the name to `.env` and
generates `sandbox/__init__.py`, the literal declaration Managed Deep Agents reads. MDA provisions
its own sandbox per thread from that file; `mda check` warns when the two disagree. Both the
build and the probe need a LangSmith key with sandbox permissions; a key without them fails with
"No matching RBAC permission". If the gateway key is a different key, keep it in
`LANGSMITH_GATEWAY_API_KEY` and set `PAID_MEDIA_MODEL_API_KEY_ENV=LANGSMITH_GATEWAY_API_KEY`.
Snapshots built from a Dockerfile resolve by id, which is what `publish` stores. A process
sandbox is deleted on exit, and by the platform shortly after its idle TTL if the process died.

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
