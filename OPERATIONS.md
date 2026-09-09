# Operations

## Prerequisites

- Python 3.11 or newer and `uv`
- a tool-calling model key for live model runs (the fixture demo needs none)
- a Pipeboard token only for live platform reads; direct-platform credentials only for LinkedIn,
  X, and OpenAI Ads
- a LangSmith API key with deployment permissions for `mda dev`, `mda deploy`, and sandbox snapshots

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
| `uv run paid-media-agent doctor [--snapshot]` | Configuration, packages, catalog, approvals, PDF, and sandbox checks; `--snapshot` runs the sandbox contract |
| `uv run paid-media-agent config show\|set KEY=VALUE\|generate KEY` | Read or change `.env` without printing secrets; generate the approval signing key |
| `uv run paid-media-agent test model\|pipeboard\|all` | Connection tests that never print secret values |
| `uv run paid-media-agent accounts discover\|list\|add\|remove` | Host-side account discovery and alias mapping (six platforms) |
| `uv run paid-media-agent org show\|interview\|set field=value\|add-link URL\|add-file PATH` | Your organization's context (goals, conversions, targets, naming, approvers, shared docs) in `docs/org` |
| `uv run paid-media-agent catalog show [--live]` | The authorized tool catalog: reads, admitted mutations, denied tools |
| `uv run paid-media-agent policy validate [--live]` | Validate the write policy against the fixture or live catalog |
| `uv run paid-media-agent ask "question"` | One question, locally, through the same profile the deployment runs |
| `uv run paid-media-agent report --cadence weekly\|monthly [--end DATE]` | Deterministic cross-platform report, HTML and PDF |
| `uv run paid-media-agent mda check\|dev\|deploy [--yes]` | Managed Deep Agents preflight, local managed run, hosted deploy |
| `uv run paid-media-agent sandbox publish\|use\|test` | Build, declare, and probe the snapshot behind MDA's per-thread sandbox |
| `uv run paid-media-agent writes kill-switch on\|off` | Incident switch for live writes |
| `uv run mda dev` / `uv run mda deploy .` | The Managed Deep Agents CLI itself; the console starts these for you |

Optional native dependency: PDF reports use WeasyPrint (`reports` extra), which needs Pango and
Cairo system libraries (`brew install pango` on macOS, `libpango-1.0-0 libcairo2` on Debian).
Without them reports render as HTML only and `doctor` reports `report_pdf` as a warning. The
managed build has no native libraries either; bake them into the sandbox snapshot (below) when
PDFs matter.

## Deploying with Managed Deep Agents

`mda deploy .` compiles `agent.py`, syncs `instructions.md` and `skills/` (the business wiki is
the skill `paid-media-wiki`) as managed context, forwards the non-reserved values of `.env` as
deployment secrets, registers the schedules, and provisions the Slack app declared in
`channels/slack.py`. On the first deploy the CLI prints a Slack authorization link: open it, pick
the workspace, approve, then return to the terminal and press Enter so the CLI can verify the
grant and finish provisioning. Approve the link while signed into the LangSmith organization that
owns the deployment; the grant is recorded there, and the CLI prints the link again if it landed
elsewhere. Run the deploy from an interactive terminal for that step; a non-interactive run stops
at "Slack channel setup requires authorization" every time.

After provisioning the agent sends you a Slack direct message. Reply to it to start a run, or
mention the app in a channel it has been invited to; replies in the same thread continue the
conversation. A proposed change arrives as a card with Approve and Reject. Approval is recorded
against the identity MDA presents for the person who clicked, and only identities listed in
`PAID_MEDIA_APPROVER_IDS` count; a refused approval names the identity it saw, so paste that into
the list (console step Deploy, or `config set`) and redeploy. Edits are not available from the
managed card; ask the agent for a revised proposal instead.

The deployment costs money while it exists. `uv run mda delete` removes it, its sandboxes, and
its snapshots.

### What the hosted agent can and cannot read

The model's filesystem in the deployment is the MDA sandbox. It holds `/skills` (synced by MDA,
wiki included) and `/workspace` (the thread's scratch space). It does not hold the repository,
so everything else reaches the model through host tools: `get_org_context` for the organization
profile and shared briefs, `compare_periods` and `summarize_window` for artifacts, and
`render_report` for files. Host-written artifacts live on the deployment's disk, not in the
sandbox; the model works with their ids.

The organization profile (`docs/org/`) travels with the deploy from your checkout. Answers the
agent saves in the hosted deployment live on that deployment's disk until the next deploy, so run
the interview locally (console or CLI) before deploying and treat hosted answers as provisional.

## Organization context

`docs/org/` holds what only your organization knows: what you sell, the conversion that counts,
targets or "directional", monthly budget, markets and timezone, seasonality, campaign naming, and
who approves changes, plus links and text files you share. It is ignored by git. Fill it from
the console step "Your business", from `paid-media-agent org interview`, or by asking the agent
to learn about your business (skill `paid-media-org-onboarding`, tools `get_org_context`,
`update_org_profile`, and `add_org_source`). The agent calls `get_org_context` before every
analysis and says "not provided" rather than guessing when a field is empty. The "who approves"
answer is the human list the agent names; the identities that can actually approve are
`PAID_MEDIA_APPROVER_IDS`. Links must be public https pages under 1 MB; files
must be text (`.md`, `.txt`, `.csv`, `.json`, `.html`).

## Synthetic data

The fixture datasets ship with August 2026 dates but are served anchored to today: the newest
complete day is two days ago, and each platform keeps its shipped reporting lag. Set
`PAID_MEDIA_FIXTURE_ANCHOR=2026-08-28` to reproduce a specific window (the test suite pins this).

## Self-hosting

Not on `main`. The self-hosted API, Postgres persistence, the rich Slack adapter, the local
LangGraph Server, and the Docker files live on the `self-hosted` branch; see
[docs/self-hosting.md](docs/self-hosting.md).

## Live checks

The default test suite is offline. Live, read-only checks are opt-in:

```bash
PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q
```

They require `PIPEBOARD_API_TOKEN` for the catalog check and a LangSmith key with sandbox
permissions plus a declared snapshot for the sandbox probe. They never call a provider mutation.

## Source refresh

Before changing a claim about Deep Agents, MDA, model support, provider tool search, Slack, or
Pipeboard, refresh the relevant official source in [docs/sources/official-links.md](docs/sources/official-links.md).
Before changing paid-media doctrine, update [skills/paid-media-wiki/sources.md](skills/paid-media-wiki/sources.md).

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
- the MDA definition and the local CLI compile the same agent assembly;
- the Block Kit renderers produce the same presentation objects the managed card shows;
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
`--json`. The console writes `.env` and `config/accounts.toml` locally, starts the two fixed-template
processes (`mda dev`, and `mda deploy` with confirmation) with logs under `workspace/logs/`, and
exposes the kill switch. It is not a hosted admin panel: do not expose the port, and prefer
deployment secrets over `.env` in production.

The wizard has six steps: Model, Ad accounts, Your business, Try it, Deploy, Done. "Try it" runs
one question locally through the deployment's profile; "Deploy" collects the LangSmith key and
the approver identities, runs the preflight, and starts `mda dev` or `mda deploy`.

## Local run with LangSmith Studio

`uv run mda dev` starts the managed runtime locally against your `.env` and opens the agent in
LangSmith Studio, where every tool call and the approval interrupt are visible. It needs a
LangSmith key; it does not need a Pipeboard token (without one the fixture accounts are used).

## Sandbox snapshot

Managed Deep Agents gives every thread its own sandbox as the model's filesystem and syncs
`skills/` into it. By default it uses the platform image, which is enough for reads, analysis,
governed writes, and HTML reports. `sandbox/Dockerfile` is the optional reproducible image with
WeasyPrint's native libraries and a pinned toolchain:

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # LangSmith builds sandbox/Dockerfile
uv run paid-media-agent sandbox test --json                              # open a probe sandbox, check, delete
```

`publish` (or `sandbox use <id>` for an existing snapshot) writes the snapshot id to `.env` and
generates `sandbox/__init__.py`, the literal declaration MDA reads; `mda check` warns when the two
disagree. Both the build and the probe need a LangSmith key with sandbox permissions; a key
without them fails with "No matching RBAC permission". If the gateway key is a different key,
keep it in `LANGSMITH_GATEWAY_API_KEY` and set `PAID_MEDIA_MODEL_API_KEY_ENV=LANGSMITH_GATEWAY_API_KEY`.
Snapshots built from a Dockerfile resolve by id, which is what `publish` stores. The model never
gets a shell: `execute` stays hidden, and host code uses the sandbox shell only in the probe.

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
deterministic pipeline locally. In the deployment, `schedules/weekly_report.py` and
`schedules/monthly_report.py` start the agent on a cron with a prompt that asks for the report;
any change it might propose still waits for a human approval.
