# Operations

## Setup

Use Python 3.11+ and [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run paid-media-agent demo --with-proposal
```

For setup with a coding agent, use the [onboarding skill](.agents/skills/paid-media-onboarding/SKILL.md).
The optional `uv run paid-media-agent setup` console configures keys, accounts, and deployment.
Business context is Markdown in `workspace/skills/company-context/`; see
[Customization](docs/customization.md).

Keep keys in `.env` or deployment secrets. Use `config show` for masked configuration. Commands
load allowlisted keys from the project `.env`; nonblank saved values take precedence over the
shell. The console is local-only. Do not expose its port as a hosted admin panel.

## Commands

Add `--help` for options and `--json` where supported for machine-readable output.

| Command | Purpose |
| --- | --- |
| `uv run paid-media-agent setup` | Optional browser setup for connections and deployment |
| `uv run paid-media-agent config show` | Inspect masked configuration |
| `uv run paid-media-agent config set KEY=VALUE` | Save local configuration |
| `uv run paid-media-agent config generate KEY` | Generate an API token or approval signing key |
| `uv run paid-media-agent models --provider langsmith --json` | Read the provider's current model list |
| `uv run paid-media-agent test model` | Send a short request to the configured model |
| `uv run paid-media-agent test pipeboard` | Check connected tool catalogs |
| `uv run paid-media-agent accounts discover` | Discover accessible accounts |
| `uv run paid-media-agent accounts list` | Show configured aliases |
| `uv run paid-media-agent catalog show` | Inspect tool admission and schemas |
| `uv run paid-media-agent policy validate` | Validate the write policy against the current catalog |
| `uv run paid-media-agent doctor` | Check configuration, dependencies, and runtime prerequisites |
| `uv run paid-media-agent demo --with-proposal` | Offline analysis and simulated approved change |
| `uv run paid-media-agent ask "Compare campaign performance last week"` | Run a question with your configured model |
| `uv run paid-media-agent report --cadence weekly` | Render a report without a model |
| `uv run paid-media-agent writes kill-switch on` | Stop mutations |
| `uv run paid-media-agent mda check` | Validate the local MDA project |
| `uv run paid-media-agent sandbox test --json` | Probe an explicitly configured sandbox snapshot |
| `uv run paid-media-agent serve` | Start the self-hosted API |
| `uv run paid-media-agent slack` | Start the self-hosted Slack Socket Mode adapter |

## Deploying with Managed Deep Agents

Requires a LangSmith organization with MDA access, a deployment API key, and a model-provider key.
MDA is available in US LangSmith Cloud. See the current
[quickstart](https://docs.langchain.com/langsmith/python/managed-deep-agents-quickstart).

```bash
uv run paid-media-agent mda check
uv run mda deploy .
```

MDA builds the project, syncs instructions and runtime skills to Context Hub, provisions the
sandbox, and configures the native Slack channel. If prompted, open the Slack authorization link,
authorize your workspace, and return to the terminal. The console offers **Continue deployment**
for the same handoff. After success, open the printed LangSmith deployment URL or the agent's Slack DM.

MDA's deployment status and a successful agent response establish readiness. Local preflight does
not verify your cloud permissions. [Hosting is paid](https://www.langchain.com/pricing).
`uv run mda delete` removes the deployment and its managed sandboxes and snapshots.

For development, `uv run mda dev .` opens the managed runtime in LangSmith Studio. Inspect model
calls, tool results, and approval interrupts there.

### Identity and memory

`identity.py` uses LangSmith API-key authentication. Anyone with that workspace key can call the
agent. For end-user private conversations, configure MDA's
[Supabase identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity).
Approval authority remains a separate host-owned configuration.

Durable memory is off by default. Enable MDA's native `memory.py` declaration only when all callers
may share learned knowledge. See [Customization](docs/customization.md#memory-and-reports).

### Slack settings

Edit `channels/slack.py` or save these optional values with `config set`, then redeploy:

| Setting | Default |
| --- | --- |
| `PAID_MEDIA_SLACK_NAME` | Paid Media Agent |
| `PAID_MEDIA_SLACK_DESCRIPTION` | Cross-account campaign analysis description |
| `PAID_MEDIA_SLACK_BACKGROUND_COLOR` | Platform default |
| `PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES` | `false`: mentions, direct messages, and active-thread replies |
| `PAID_MEDIA_SLACK_ALLOW_BOT_TRIGGERS` | `false` |

A custom icon is `channels/slack-icon.png`: a 512 × 512 PNG under 1 MB. The console can upload it.
MDA supplies Slack rendering and approve/reject interactions. This project does not add custom
paid-media cards to the managed channel.

### Reports and schedules

`schedules/weekly_report.py` and `schedules/monthly_report.py` are native MDA declarations. By
default, they run Monday at 13:00 UTC and the first day of the month at 13:00 UTC. The weekly report
compares two 7-day windows; the monthly report compares two 28-day windows. Remove a schedule file
and redeploy to disable it. Use the [delivery example](docs/customization.md#memory-and-reports)
to post the final response to your Slack channel. Without `deliver_to`, results stay in LangSmith.

Edit the static cron, timezone, prompt, and destination in those files. The console also supports
time/day changes through `PAID_MEDIA_REPORT_TIME`, `PAID_MEDIA_REPORT_TIMEZONE`,
`PAID_MEDIA_WEEKLY_REPORT_DAY` (0 Monday to 6 Sunday), and `PAID_MEDIA_MONTHLY_REPORT_DAY` (1–28).
Use `config set` for these environment settings so their schedule declarations stay synchronized.
A waited `mda deploy .` reconciles schedules; `--no-wait` skips that step.

The local `report` command uses known campaign-performance adapters. Other provider schemas can
be explored through `ask`; they need a normalization mapping before inclusion in typed reports.
HTML reports render on the host. PDF rendering requires WeasyPrint and its native libraries in the
host process. A sandbox snapshot does not install libraries into that process. Automatic Slack
PDF uploads are not included. Use the self-hosted artifact API or local output files for downloads.

### Sandbox

MDA bakes `sandbox/setup.sh` automatically and reuses the resulting snapshot for new threads.
The recipe installs Python tools and PDF libraries. Changes to the recipe rebuild the snapshot;
existing thread sandboxes retain their files until expiry. MDA owns provisioning and cleanup.

The model reads synced skills under `/skills` and uses `/workspace` for thread scratch files.
Host-created analysis artifacts stay on the host and are accessed through analysis tools. The
current tool policy exposes filesystem operations but no arbitrary shell or subagent execution.

Optional standalone snapshot tools:

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox
uv run paid-media-agent sandbox test --json
```

`publish` builds the same recipe, saves the snapshot ID locally, and updates the sandbox bake base.
The probe needs an explicit snapshot; it does not resolve MDA's deployment-owned recipe snapshot.

## Self-hosting

Install `self-host`, `slack`, and `reports` extras, or use the Docker image. Follow
[Self-hosting](docs/self-hosting.md) for API credentials, Postgres, Slack tokens, and hosting.
Compose includes PDF libraries and persists checkpoints and local artifacts. Your scheduler runs
the report command; MDA cron declarations are not a self-hosted scheduler.

The API and Slack share the same model, catalog, analysis, reports, and approval rules as MDA.
Slack uses native status and streaming with generic tool progress. Keep any customization in the
shared tools and skills, not tool-specific message renderers.

## Direct platforms

Pipeboard connects Google Ads, Meta Ads, TikTok Ads, Pinterest Ads, Snap Ads, Reddit Ads, LinkedIn
Ads, and Google Analytics. Catalogs load concurrently; tool selection keeps full schemas out of
every model request. Account discovery is host-side. Unknown or unscoped tools are excluded.

X Ads and OpenAI Ads have read-only direct adapters. Set their keys in `.env`, then run
`accounts discover` and map the accounts. X uses OAuth 1.0a. OpenAI Ads requires advertiser API
access. LinkedIn connects through Pipeboard.

Do not infer a connection from a saved key. Check the catalog and one real read before relying on it.

## Models

`PAID_MEDIA_MODEL` accepts `provider:model`. Anthropic and OpenAI ship with the base install.
The LangSmith Gateway uses `langsmith:provider/model`. Other providers have optional extras:
`google`, `groq`, `xai`, `mistral`, and `deepseek`.

For an OpenAI-compatible endpoint, set `PAID_MEDIA_MODEL_BASE_URL` and
`PAID_MEDIA_MODEL_API_KEY_ENV` to the name of its key environment variable. Native tool search is
used only for verified models and endpoints; other models use the portable tool selector.

## Writes

Account changes are disabled by default. The [live-write runbook](docs/operations/live-write-runbook.md)
covers reviewed tool policies, approver identities, catalog pinning, and the kill switch.
MDA's approval interrupt does not replace the host's policy or digest checks.

Proposal/receipt repositories in the default MDA profile are process-local. A restart loses pending
proposals and they must be recreated; the code fails closed. Use the self-hosted Postgres profile
when durable proposal records are required. Managed thread persistence alone does not persist
these application repositories.

## Verification

```bash
uv sync --all-extras --dev
make check
uv run paid-media-agent demo --with-proposal
```

Tests are offline by default. `PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q` opts into
read-only integration checks with your configured credentials. No automated test executes a live
provider mutation. Synthetic data is anchored two days before today; set
`PAID_MEDIA_FIXTURE_ANCHOR=2026-08-28` to reproduce the shipped windows.

Refer to [official sources](docs/sources/official-links.md) before changing provider or MDA contracts.
