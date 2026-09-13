# Operations

## Prerequisites

- Python 3.11 or newer and `uv`
- a tool-calling model key for live model runs (the fixture demo needs none)
- a Pipeboard token only for live platform reads; direct-platform credentials only for LinkedIn,
  X, and OpenAI Ads
- a LangSmith API key with deployment permissions for `mda dev`, `mda deploy`, and sandbox snapshots
- for self-hosting: Docker (or Postgres and Python), and Slack bot and app tokens for the rich adapter

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
`export`. Nonblank saved values take precedence over the shell. Blank entries preserve shell values unless
the console previously exported that key, in which case clearing it removes the export. Every command has `--json` where a
machine reads it, and the setup console runs the same actions.

| Command | What it does |
|---|---|
| `uv run paid-media-agent models --provider langsmith --json` | List current models from the selected provider's official API using its configured key; no prompt or configuration write |
| `uv run paid-media-agent setup [--port] [--no-open] [--no-token]` | Local onboarding console over the actions below; `--no-token` for a coding agent's browser pane; the port defaults to `$PORT`, then 8765 |
| `uv run paid-media-agent demo [--with-proposal]` | Fixture run through the real graph, optionally with a governed write |
| `uv run paid-media-agent doctor [--snapshot]` | Configuration, packages, catalog, approvals, PDF, and sandbox checks; `--snapshot` runs the sandbox contract |
| `uv run paid-media-agent config show\|set KEY=VALUE\|generate KEY` | Read or change `.env` without printing secrets; generate the approval signing key and API tokens |
| `uv run paid-media-agent test model\|pipeboard\|slack\|db\|all` | Connection tests that never print secret values (`all` adds Slack and Postgres on the self-hosted path) |
| `uv run paid-media-agent accounts discover\|list\|add\|remove` | Host-side account discovery and alias mapping (eight Pipeboard platforms plus two direct connections) |
| `uv run paid-media-agent org show\|interview\|set field=value\|add-link URL\|add-file PATH` | Your organization's context (goals, conversions, targets, naming, approvers, shared docs) in `docs/org` |
| `uv run paid-media-agent catalog show [--live]` | The authorized tool catalog: reads, admitted mutations, denied tools |
| `uv run paid-media-agent policy validate [--live]` | Validate the write policy against the fixture or live catalog |
| `uv run paid-media-agent ask "question"` | One question, locally, through the same profile the deployment runs |
| `uv run paid-media-agent report --cadence weekly\|monthly [--end DATE]` | Deterministic cross-platform report, HTML and PDF |
| `uv run paid-media-agent mda check\|dev\|deploy [--yes]` | Managed Deep Agents preflight, local managed run, hosted deploy |
| `uv run paid-media-agent serve [--host] [--port]` | Self-hosted API; mounts the signed Slack HTTP transport when `SLACK_TRANSPORT=http` |
| `uv run paid-media-agent slack` | Rich Slack adapter in Socket Mode against the self-hosted runtime |
| `uv run paid-media-agent sandbox publish\|use\|test` | Build, declare, and probe the snapshot behind MDA's per-thread sandbox |
| `uv run paid-media-agent writes kill-switch on\|off` | Incident switch for live writes |
| `uv run mda dev` / `uv run mda deploy .` | The Managed Deep Agents CLI itself; the console starts these for you |

Optional native dependency: PDF reports use WeasyPrint (`reports` extra), which needs Pango and
Cairo system libraries (`brew install pango` on macOS, `libpango-1.0-0 libcairo2` on Debian).
Without them reports render as HTML only and `doctor` reports `report_pdf` as a warning. The
Docker image includes them. The MDA sandbox recipe includes them too, but that does not install
them in the separate Agent Server where report tools currently render. `serve` needs the
`self-host` extra and `PAID_MEDIA_API_TOKENS`
(`token:caller,...`); the bearer a client sends is the part before `:caller`.

## Deploying with Managed Deep Agents

`mda deploy .` compiles `agent.py` and syncs `instructions.md` and `skills/` as managed context.
`skills/` links to `.agents/skills/`, including the `paid-media-wiki` skill. The CLI forwards the
non-reserved values of `.env` as deployment secrets, registers the schedules, and provisions the Slack app declared in
`channels/slack.py`. On the first deploy the CLI prints a Slack authorization link: open it, pick
the workspace, approve, then return to the terminal and press Enter so the CLI can verify the
grant and finish provisioning. Approve the link while signed into the LangSmith organization that
owns the deployment; the grant is recorded there, and the CLI prints the link again if it landed
elsewhere. In the setup console, select **Continue deployment** after authorization; the console
sends Enter to the waiting process. A non-interactive invocation without this continuation stops
at "Slack channel setup requires authorization".

After provisioning the agent sends you a Slack direct message. Reply to it to start a run, or
mention the app in a channel it has been invited to; replies in the same thread continue the
conversation. A proposed change arrives as a card with Approve and Reject. Approval is recorded
against the identity MDA presents for the person who clicked, and only identities listed in
`PAID_MEDIA_APPROVER_IDS` count; a refused approval names the identity it saw, so paste that into
the list (Advanced → Managed Deep Agents, or `config set`) and redeploy. Edits are not available from the
managed card; ask the agent for a revised proposal instead.

The deployment costs money while it exists. `uv run mda delete` removes it, its sandboxes, and
its snapshots.

### Customize the managed agent

Deployment uses a single column. **Agent settings** is a separate card below the LangSmith setup,
with message triggers and weekly/monthly report timing visible. **Slack appearance** expands to show
the name, description, icon, background, and preview. Settings save with **Deploy agent**, with no
separate save step. The deployment action sits
at the bottom, after the setup, agent settings, and optional local development controls.
Weekday and monthly-date dropdowns retain native keyboard interaction and use the CORE popup styling
in browsers that support customizable selects. UI transitions are brief; keyboard input and reduced
motion skip them.
New LangSmith users can open account creation, plans, and API-key settings in a new browser tab
without losing their setup draft. A saved API key does not prove MDA access or an active plan. Branding and timing apply on the next MDA deployment.
The Slack display name does not rename the deployment. Self-hosted Slack appearance is configured
in your own Slack app settings.

The same non-secret settings are available to coding agents through `config show` and `config set`:

```bash
uv run paid-media-agent config set PAID_MEDIA_SLACK_NAME="Campaign Analyst"
uv run paid-media-agent config set PAID_MEDIA_REPORT_TIME=09:30 PAID_MEDIA_REPORT_TIMEZONE=America/Los_Angeles PAID_MEDIA_WEEKLY_REPORT_DAY=0 PAID_MEDIA_MONTHLY_REPORT_DAY=1
```

| Setting | Default / constraint |
| --- | --- |
| `PAID_MEDIA_SLACK_NAME` | Paid Media Agent; 1–35 letters, numbers, spaces, underscores, dashes or periods; no leading/trailing space or dash |
| `PAID_MEDIA_SLACK_DESCRIPTION` | At most 139 characters |
| `PAID_MEDIA_SLACK_BACKGROUND_COLOR` | Empty, or `#RRGGBB` |
| `PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES` | `false`; mentions and DMs start runs, replies continue active threads |
| `PAID_MEDIA_SLACK_ALLOW_BOT_TRIGGERS` | `false`; enabling can cause repeated bot-to-bot runs |
| `PAID_MEDIA_REPORT_TIME` / `PAID_MEDIA_REPORT_TIMEZONE` | `13:00` / `UTC`; time to the minute and an IANA timezone |
| `PAID_MEDIA_WEEKLY_REPORT_DAY` / `PAID_MEDIA_MONTHLY_REPORT_DAY` | `0` (Monday, through 6 Sunday) / `1` (through 28) |

The console validates a still 512 × 512 PNG up to 1 MB and saves it as `channels/slack-icon.png`.
That local file stays out of Git but is included in MDA builds. Without it, MDA generates an icon.
A coding agent can place a valid PNG at that path; remove it to return to the generated icon.

MDA requires static schedule declarations. Saving report timing through setup or `config set`
updates `.env` and only the `cron`/`timezone` literals in `schedules/weekly_report.py` and
`schedules/monthly_report.py`. Existing report prompts and reporting windows are preserved.
If you edit report timing directly in `.env`, run `config set` with those values to synchronize
the declarations; the project preflight flags a mismatch. Report delivery destinations remain
part of the authored schedule. Approval and live-write gates are unchanged.

### What the hosted agent can and cannot read

The model's filesystem in the deployment is the MDA sandbox. It holds `/skills` (synced by MDA,
wiki included) and `/workspace` (the thread's scratch space). It does not hold the repository,
so everything else reaches the model through host tools: `get_org_context` for the organization
profile and shared briefs, `compare_periods` and `summarize_window` for artifacts, and
`render_report` for files. Host-written artifacts live on the deployment's disk, not in the
sandbox; the model works with their ids.

The organization profile (`docs/org/`) travels with the deploy from your checkout. Answers the
agent saves in the hosted deployment live on that deployment's disk until the next deploy, so run
the interview locally (chat or CLI) before deploying and treat hosted answers as provisional.

## Organization context

`docs/org/` holds what only your organization knows: what you sell, the conversion that counts,
targets or "directional", monthly budget, markets and timezone, seasonality, campaign naming, and
who approves changes, plus links and text files you share. It is ignored by git. Fill it from
the CLI (`paid-media-agent org interview`), or by asking the coding agent in chat to learn
about the business (skill `paid-media-org-onboarding`, tools `get_org_context`,
`update_org_profile`, and `add_org_source`). The setup console does not collect it. The agent
calls `get_org_context` before every
analysis and says "not provided" rather than guessing when a field is empty. The "who approves"
answer is the human list the agent names; the identities that can actually approve are
`PAID_MEDIA_APPROVER_IDS`. Links must be public https pages under 1 MB; files
must be text (`.md`, `.txt`, `.csv`, `.json`, `.html`).

## Synthetic data

The fixture datasets ship with August 2026 dates but are served anchored to today: the newest
complete day is two days ago, and each platform keeps its shipped reporting lag. Set
`PAID_MEDIA_FIXTURE_ANCHOR=2026-08-28` to reproduce a specific window (the test suite pins this).

## Self-hosting

`docker compose up` builds the API image (Pango and Cairo included, so PDFs render) and starts
Postgres with `DATABASE_URL` set for the API. Keys come from your local `.env` through
`env_file`; the image copies no env file. Without Docker: `uv sync --extra self-host --extra
slack`, set `DATABASE_URL` (or leave it empty for in-memory state), generate `PAID_MEDIA_API_TOKENS`
and `PAID_MEDIA_APPROVAL_SIGNING_KEY` with `config generate`, then `paid-media-agent serve` and
`paid-media-agent slack`. The rich Slack adapter needs an app created from
`config/slack-manifest.example.yaml`; Socket Mode needs no public URL. Approvers are
`slack:<team_id>:<user_id>` refs or API caller names. The walkthrough is
[docs/self-hosting.md](docs/self-hosting.md); the console's "Self-host" step runs the same actions.
The console groups storage and API credentials first, optional Slack second, and the Docker command
last. Existing-database settings and running the API directly are expandable alternatives.

## Live checks

The default test suite is offline. Live, read-only checks are opt-in:

```bash
PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q
```

They require `PIPEBOARD_API_TOKEN` for the catalog check, `DATABASE_URL` for the Postgres
round-trip, and a LangSmith key with sandbox permissions plus a declared snapshot for the sandbox
probe. They never call a provider mutation.

## Source refresh

Before changing a claim about Deep Agents, MDA, model support, provider tool search, Slack, or
Pipeboard, refresh the relevant official source in [docs/sources/official-links.md](docs/sources/official-links.md).
Before changing paid-media doctrine, update [.agents/skills/paid-media-wiki/sources.md](.agents/skills/paid-media-wiki/sources.md).

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
- the MDA definition, the self-hosted runtime, and the local CLI compile the same agent assembly;
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

`uv run paid-media-agent setup [--port 8765] [--no-open] [--no-token]` serves
`src/paid_media_agent/admin/` on 127.0.0.1 with a per-run admin token in the URL fragment.
Coding agents with a browser pane cannot pass a fragment, so `--no-token` serves the console at
the plain URL and accepts same-origin calls only (the `Origin` and `Sec-Fetch-Site` headers a
browser always sends); a page on another site still cannot drive it. `.claude/launch.json` holds
a `setup` entry that Claude Code desktop starts and shows in its Browser pane. Cursor and the
Codex app open the same URL in their browser panes using the instructions in `AGENTS.md`. On macOS
the launch configuration can only start when the app has access to the folder holding the
checkout (Desktop, Documents, and Downloads are protected); a launched server that exits at
`getcwd` with "Operation not permitted" needs that permission granted, or the checkout moved. Every page action calls the same
functions as the CLI subcommands (`admin/actions.py`), so agents can script the same steps with
`--json`. The console writes `.env` and `config/accounts.toml` locally, starts fixed-template processes
(`mda dev`, `mda deploy` with confirmation, `serve`, `slack`) with logs under `workspace/logs/`,
and exposes the kill switch. It is not a hosted admin panel: do not expose the port, and prefer
deployment secrets over `.env` in production.

The first-run flow is **Welcome → Model → Accounts → Deployment**. The welcome leads directly
to model setup, which tests one short request and advances only
on success. Connection checks expire when their settings change. Saved configuration alone is
not a successful connection check.

Choose sample data or connect and discover real accounts. `PAID_MEDIA_DATA_MODE=sample` forces
fixture tools and sample aliases across the CLI and deployed profiles even when live credentials
are saved. `live` requires credentials and does not add fixture platforms; `auto` selects based
on credentials. A real model may charge for sample questions. The CLI demo uses a scripted
model and disables tracing. Organization context belongs in `paid-media-agent org interview` or
the coding agent's chat, not a setup form.

Deployment recommends **Managed Deep Agents**, with paid hosting clearly labeled. Supply a
LangSmith key if one is not already saved. **Deploy agent** saves the runtime
choice, runs a local project check, and starts the fixed `mda deploy .` command. No separate
check or Studio visit is required. A failed check prevents the deploy process from starting.
The project check does not verify cloud deployment permission; MDA checks that when deploying.

If MDA prints a Slack authorization prompt, finish the linked authorization and select
**Continue deployment**. The server sends only Enter to the recognized waiting process. Status,
errors, retries, and output stay on the deployment screen. An active process is not evidence of a
healthy deployment. After successful completion, open the agent's Slack message or LangSmith.
Managed Deep Agents and Self-host are visible choices with expandable details. Studio is under **Develop locally**; the CLI also works without deployment.
Self-hosting starts with Docker/API and Postgres, with Slack optional.

The console is plain HTML, CSS, and JavaScript served by Python. It contains no conversation
client, frontend build, or streaming service. Use Slack, Studio, or the existing API for the agent.
Advanced groups connections and hosting in separate expandable cards, using the same design
tokens as Setup. Commands sit below the controls. Approval configuration and write-gate controls
remain in the CLI and live-write runbook; the console does not expose them. Runtime approval
enforcement is unchanged. Advanced deployment returns to Setup to review settings before upload.

## Local run with LangSmith Studio

`uv run mda dev` starts the managed runtime locally against your `.env` and opens the agent in
LangSmith Studio, where every tool call and the approval interrupt are visible. It needs a
LangSmith key; it does not need a Pipeboard token (without one the fixture accounts are used).

## Sandbox snapshot

Managed Deep Agents gives every thread its own sandbox as the model's filesystem and syncs
`skills/` into it. The project ships a `sandbox/__init__.py` declaration and `sandbox/setup.sh`.
`mda deploy` / `mda dev` automatically bake the recipe from Python 3.13 with ripgrep, jq, Jinja2,
WeasyPrint 70, Pango, Cairo, and fonts. The recipe verifies PDF rendering before the bake succeeds.
No separate sandbox setup is needed. MDA reuses the recipe snapshot until the script or base
changes; existing thread sandboxes keep their files. The deployment preflight checks that the
declaration and recipe exist. For optional standalone builds and probes:

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # LangSmith builds sandbox/Dockerfile
uv run paid-media-agent sandbox test --json                              # open a probe sandbox, check, delete
```

`publish` (or `sandbox use <id>` for an existing snapshot) writes the snapshot id to `.env` and
updates `sandbox/__init__.py`, the literal bake-base declaration MDA reads. The Dockerfile uses
the same `setup.sh`, and the standalone build context contains only those two files. `sandbox test`
requires an explicitly published snapshot; it does not resolve MDA's deployment-owned snapshot.
Both automatic and standalone builds need a LangSmith key with sandbox permissions; a key
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

The Accounts step uses one connection list. Pipeboard shows Google, Meta, TikTok, Pinterest, Snap,
Reddit, LinkedIn, and Google Analytics together, with a link to connect them in Pipeboard and one token form.
X and OpenAI Ads have their own rows and open their credential forms under
Advanced · Direct connections (route `direct`), followed by the same
account discovery as Pipeboard. `paid-media-agent accounts discover`
lists direct accounts next to Pipeboard ones once their credentials are in `.env`.

X Ads and OpenAI Ads use direct connectors. Set their credentials in `.env`
(see `.env.example`); the runtime adds their read tools to the catalog on startup and
`paid-media-agent accounts discover` lists their accounts next to Pipeboard's. X requests are signed with OAuth 1.0a.

LinkedIn uses `https://linkedin-ads.mcp.pipeboard.co/`. Existing direct LinkedIn credentials remain
usable from the CLI when no Pipeboard token is configured; with a Pipeboard token, its MCP owns
LinkedIn discovery and reads so saved direct credentials cannot override it.

## Scheduled reports

The console uses matching dropdowns for weekday, monthly day, and report time. Time offers
quarter-hour intervals and retains an existing custom minute value. Use `config set` for other
minute values; the saved time and timezone are shared by both report schedules.

`paid-media-agent report --cadence weekly|monthly [--end YYYY-MM-DD] [--alias a]` runs the
deterministic pipeline locally. In the deployment, `schedules/weekly_report.py` and
`schedules/monthly_report.py` start the agent on a cron with a prompt that asks for the report;
any change it might propose still waits for a human approval.
