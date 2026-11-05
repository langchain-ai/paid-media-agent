# Operations

## Setup

Use Python 3.12+ and [uv](https://docs.astral.sh/uv/):

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
uv run mda deploy
```

Requires `managed-deepagents` 0.10.1 or later (`uv sync` installs it). MDA builds the project,
syncs instructions and runtime skills to Context Hub, provisions the sandbox, and configures the
native Slack channel. A first deploy asks which Slack app to use: one LangSmith creates and manages,
a new one from a manifest, or one you already have. When Slack still needs you (authorizing
LangSmith, installing or approving the app), deploy prints the link and waits until Slack reports it
done. The console offers **Continue deployment** for the same handoff. After success, open the
printed LangSmith deployment URL or the agent's Slack DM. `uv run mda channels setup` checks or
finishes the Slack setup later without deploying.

`mda deploy` creates a **serverless** deployment by default, which can scale to zero. Proposals,
approvals, receipts, and analysis artifacts in the MDA profile are process-local (see
[Writes](#writes)), so a scale-down between a proposal and its approval loses the proposal and the
approval is refused. That fails closed, but the change has to be proposed again. Before enabling live
writes, deploy with `uv run mda deploy --deployment-type dedicated`. Existing deployments keep
their type. In 0.10, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, and `LANGSMITH_WORKSPACE_ID` come
from your shell first and the project `.env` second; unset a stale shell value if deploy targets the
wrong workspace.

MDA's deployment status and a successful agent response establish readiness. Local preflight does
not verify your cloud permissions. [Hosting is paid](https://www.langchain.com/pricing).
`uv run mda delete` removes the deployment and its managed sandboxes and snapshots.

For development, `uv run mda dev` opens the managed runtime in LangSmith Studio. Inspect model
calls, tool results, and approval interrupts there.

### Identity and memory

`identity.py` uses LangSmith API-key authentication. Anyone with that workspace key can call the
agent. For end-user private conversations, configure MDA's
[Supabase identity](https://docs.langchain.com/langsmith/python/managed-deep-agents-identity).
Approval authority remains a separate host-owned configuration.

Every run's trace names the template and its version (`ls_template: langchain-ai/paid-media-agent`)
on both deployment paths, so LangChain can count adopters; nothing about you or your people goes
with it. `PAID_MEDIA_TEMPLATE_TELEMETRY=false` turns it off.

Durable memory is off by default. Enable the shared layer in MDA's native `memory.py` only when all
callers may share learned knowledge. A personal layer mounts only for a verified person. See
[Customization](docs/customization.md#memory-and-scheduling).

### Background helpers and check-ins

On MDA the agent can hand long work to a background helper and answer later in the same thread.
Three helpers are declared in `agent.py` as async subagents: `account-puller` for pulls and
comparisons across many accounts or long windows, `report-builder` for a full rendered report, and
`general-purpose` for other read-only research. `mda build` turns each into a graph of its own
(`paid-media-agent--account-puller`, ...) on the same deployment, sharing the lead's sandbox and
trace. When a helper finishes, it wakes the lead on its thread and MDA posts the answer to the
Slack thread the request came from. Every helper is read-only: its tools are reads, comparisons,
and report rendering, with the lead's invocation guard, redaction, and call limits. Proposals and
approvals stay with the lead.

Any caller allowed to start runs on the deployment can run a helper graph directly, as themselves.
It can only read.

`schedule_check_in` lets the agent come back to a conversation later, for example two days after
an approved budget change. A check-in is a one-time MDA runtime schedule on the thread; it survives
redeploys and answers in the same conversation. It reads and reports like any run, and any change
it suggests needs a new approval. Each owner holds at most 20 runtime schedules
(`MDA_MAX_AGENT_SCHEDULES` raises it). `schedules/housekeeping.py` runs daily at 05:30 UTC,
deletes expired check-ins in code, and ends without a model call or a post.

The self-hosted server has neither: no Agent Server to launch helpers on and no durable scheduler.
There the agent does long pulls in its own turn.

### Slack settings

Edit `channels/slack.py` or save these optional values with `config set`, then redeploy:

| Setting | Default |
| --- | --- |
| `PAID_MEDIA_SLACK_NAME` | Paid Media Agent |
| `PAID_MEDIA_SLACK_DESCRIPTION` | Cross-account campaign analysis description |
| `PAID_MEDIA_SLACK_BACKGROUND_COLOR` | Platform default |
| `PAID_MEDIA_SLACK_TRIGGER_MODE` | `thread`: a mention, then every reply in that thread. `mention`: only mentions. `all`: every message in joined channels. Direct messages always start runs |
| `PAID_MEDIA_SLACK_ALLOW_BOT_TRIGGERS` | `false` |

`PAID_MEDIA_SLACK_TRIGGER_MODE` replaces `PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES`, which MDA 0.10
deprecated. If your `.env` set the old key to `true`, set `PAID_MEDIA_SLACK_TRIGGER_MODE=all`.

A custom icon is `channels/slack-icon.png`: a 512 × 512 PNG under 1 MB. The console can upload it.
MDA supplies Slack rendering, the Stop button, and approve/reject interactions. While a run works,
the channel's `status` shows its steps as Slack's plan, in paid-media phrasing ("Reading Google
Ads campaign performance", "Comparing the two periods"; `src/paid_media_agent/surfaces/progress.py`).
A phrase never carries text the model chose: no account aliases, paths, or anyone's words, and an
unknown skill, wiki page, or tool reads generically ("a guide", "a tool"). `status` is experimental in MDA 0.10.
A reply to a turn that did work ends with one line: helpers still running, minutes since the
request, and an estimated cost for the lead and its helpers, such as
`_2 helpers · 6 min · ~$0.41_`. Prices come from `src/paid_media_agent/middleware/prices.toml`; a
model it does not list shows no cost. This project adds no custom cards to the managed channel.

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
A waited `mda deploy` reconciles schedules; `--no-wait` skips that step.

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
current tool policy exposes filesystem operations but no arbitrary shell and no blocking `task`
subagent; background helpers are read-only async subagents that share the lead's sandbox.

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
Slack uses native status and streaming, with each tool call shown as a task in the same phrasing as
MDA's plan and the same footer on replies. Keep any customization in the shared tools, skills, and
phrasebook, not tool-specific message renderers.

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

`PAID_MEDIA_MODEL_EFFORT` (`low`, `medium`, `high`, `xhigh`, `max`) sets reasoning effort for
Anthropic, OpenAI, and LangSmith Gateway models; unset uses the provider's default. Other providers
refuse it at startup.

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
