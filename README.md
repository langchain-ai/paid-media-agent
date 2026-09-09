# Paid Media Agent

[![CI](https://github.com/amal-irgashev/paid-media-agent-open-source/actions/workflows/ci.yml/badge.svg)](https://github.com/amal-irgashev/paid-media-agent-open-source/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Built with Deep Agents](https://img.shields.io/badge/built%20with-Deep%20Agents-1c3c3c.svg)](https://docs.langchain.com/oss/python/deepagents/overview)

Paid Media Agent is an open-source Deep Agents application for analyzing and safely managing paid
platforms through Pipeboard. One agent, two ways to run it: Managed Deep Agents (MDA) deploys it
to Slack in one command with managed threads, a sandbox per thread, scheduled reports, and
identity; self-hosting runs the same agent behind your own API, Postgres, and Slack app with one
`docker compose up`. The repository holds the agent (instructions, skills, business wiki, tools,
write policy) and a local console and CLI that walk you through either path.

A developer should be able to:

- clone the repository and run a useful fixture-backed demo without connecting an ad account;
- choose any supported tool-calling model directly, without a LangSmith Gateway;
- connect Google Ads, Meta Ads, Reddit Ads, and other supported platforms through Pipeboard;
- ask business questions across campaigns, audiences, creatives, spend, conversions, and pipeline;
- generate reconciled reports from deterministic calculations;
- review an exact proposed change before any provider mutation runs;
- deploy to Slack with one command and get weekly and monthly reports on a schedule, or
  self-host with Docker, Postgres, and a Slack app you own.

## Architecture

The model investigates, chooses evidence, and explains results. Trusted code owns tool authorization,
account identity, arithmetic, validation, reconciliation, approval state, provider mutation, readback,
and report layout.

```text
Slack (MDA channel or your app) / API / schedule / local CLI
              |
       shared agent assembly (agent.py)
              |
  skills + business wiki + organization context + middleware
              |
 authorized Pipeboard catalog + direct adapters + deterministic tools
              |
 proposal -> approval -> one mutation -> readback -> receipt
```

Provider-native deferred tool search is used only when the selected OpenAI or Anthropic model supports
it. Other models use `LLMToolSelectorMiddleware`. Both paths finish by resolving the selected name and
schema against the same host-owned authorized catalog.

## Where it runs

| Entry | What runs it | What it is for |
|---|---|---|
| `paid-media-agent demo` | your machine, scripted model, fixture accounts | prove the install with no credentials |
| `paid-media-agent ask` / `report` | your machine, your model, the same profile the deployment runs | try questions and reports before deploying |
| `mda dev` | your machine, Managed Deep Agents runtime, LangSmith Studio | step through tool calls and approvals |
| `mda deploy .` (recommended) | LangSmith Cloud | Slack, schedules, threads, sandbox per thread, identity, in one command |
| `docker compose up` or `paid-media-agent serve` | your infrastructure | your API, Postgres, and a Slack app you own, a few more steps |

Every entry compiles the same components from `agent.py`, so what you try locally is what runs in
Slack. Business logic and tool policy never depend on where the agent runs; a surface can render
differently, but it cannot grant a capability or bypass an approval.

## Quick start

Needs Python 3.11 or newer and [uv](https://docs.astral.sh/uv/). No ad account or model key is
required for the first command.

```bash
uv sync --all-extras --dev
uv run paid-media-agent demo --with-proposal   # fixture data through the real graph, including an approval
uv run paid-media-agent setup                  # local page: model, ad accounts, try it, where it lives
```

`setup` opens a local-only onboarding page (127.0.0.1, per-run token, writes only your `.env`)
with seven steps: Model (pick a provider, test one call), Ad accounts (a scoped Pipeboard token
and the accounts the agent may read), Your business (eight plain questions, links, and files so
the agent knows your goals, conversions, targets, and naming), Try it (one real question,
locally), Where it lives (Managed Deep Agents, recommended, or self-host), then either Deploy
(LangSmith key, who may approve changes, preflight, `mda dev`, `mda deploy`) or Self-host (your
Slack app, Postgres, API tokens, `docker compose up`), and Done. The
agent can run the business interview in chat as well: ask it to learn about your business and it
saves the answers under `docs/org/`, which stays out of git. Every step shows the CLI command it
runs, so a coding agent can do the same without a browser. The full command reference is in
[OPERATIONS.md](OPERATIONS.md#command-reference).

```bash
uv run paid-media-agent doctor --json           # every check, machine-readable
uv run paid-media-agent ask "How did spend move week over week?"
uv run paid-media-agent report --cadence weekly # deterministic HTML and PDF report
uv run mda dev                                  # the managed runtime locally, with LangSmith Studio
uv run mda deploy .                             # deploy; the first run provisions Slack
docker compose up                               # self-host instead: API on :8080 with Postgres
```

![Setup welcome](docs/screenshots/setup-welcome.png)

## Platform coverage

| Platform | Path | Reads | Writes |
|---|---|---|---|
| Google Ads, Meta Ads, Reddit Ads | Pipeboard Streamable HTTP MCP | live catalog, classified by MCP annotations | admitted rows only, behind the write gates |
| LinkedIn Ads | direct adapter (`tools/direct/linkedin.py`), OAuth 2.0 bearer with refresh | accounts, campaigns, daily campaign analytics | none in v1 |
| X Ads | direct adapter (`tools/direct/x_ads.py`), OAuth 1.0a signed | accounts, campaigns, daily campaign stats | none in v1 |
| OpenAI Ads | direct adapter (`tools/direct/openai_ads.py`), bearer key | account, campaigns, daily insights | none in v1 |

Direct platforms join the same authorized catalog as Pipeboard tools whenever their credentials
are configured, so alias scope, schema validation, artifact offload, and `compare_periods` work the
same way across all six.

## Models and the LangSmith Gateway

`PAID_MEDIA_MODEL` takes `provider:model`. The recommended path for teams already on LangSmith is
the LLM Gateway: `PAID_MEDIA_MODEL=langsmith:anthropic/claude-sonnet-4-6` with `LANGSMITH_API_KEY`,
which gives one key for every provider and a trace for every call. Gateway models use the portable
tool selector; direct Anthropic and OpenAI keys unlock provider-native tool search.

## Reports

`uv run paid-media-agent report --cadence weekly` (or `monthly`) reads every alias, compares the
last complete window with the one before, and renders HTML and PDF with no model in the loop. The
MDA project ships the same runs as schedules in `schedules/`. A platform whose read fails stays
visible as unavailable and suppresses the cross-platform total.

## Deploying with Managed Deep Agents

`agent.py` exports the definition MDA needs. `instructions.md` and `skills/` (the business wiki is
the skill `paid-media-wiki`) are synced as managed context; `channels/slack.py`, `identity.py`,
`schedules/` (weekly and monthly reports), and `sandbox/` are the managed configuration. With a
LangSmith API key in `.env`:

```bash
uv run paid-media-agent mda check   # preflight
uv run mda dev                      # local managed run with LangSmith Studio
uv run mda deploy .                 # hosted deployment; provisions Slack from channels/slack.py
```

The managed build installs core dependencies only, so the Anthropic and OpenAI integration
packages (the latter also serves `langsmith:` gateway models) and Jinja2 ship in core; other
providers stay optional extras and are unavailable in a managed build unless you move them into
core. `mda deploy` needs a LangSmith key with deployment permissions; a key that can only trace
or call the gateway fails with `403 deployments:read`.

After the first deploy the agent DMs you in Slack; reply there or mention it in a channel. Every
proposed change arrives with Approve and Reject; only the identities in `PAID_MEDIA_APPROVER_IDS`
can approve, and a refused click names the identity it saw so you can add it. MDA renders that
card itself; the self-hosted Slack app renders Block Kit cards with edits and receipts.

## Self-hosting

```bash
cp .env.example .env            # add a model key; everything else has a default
docker compose up               # API on :8080 with Postgres for proposals, approvals, receipts
```

The image includes Pango and Cairo, so PDF reports render there. Create a Slack app from
`config/slack-manifest.example.yaml` and run `paid-media-agent slack` for Block Kit review cards
over Socket Mode, or set `SLACK_TRANSPORT=http` with the signing secret to serve Slack on the same
API. Approvers are `slack:<team_id>:<user_id>` refs or the caller names from
`PAID_MEDIA_API_TOKENS`. The full walkthrough is in [docs/self-hosting.md](docs/self-hosting.md).

## Start here

- [Architecture](docs/architecture/README.md) and [operations](OPERATIONS.md)
- [Paid-media business wiki](skills/paid-media-wiki/SKILL.md) the agent reads at run time
- [Self-hosting](docs/self-hosting.md)
- [Operating contract for humans and coding agents](AGENTS.md)
- [Contributing](CONTRIBUTING.md), [security policy](SECURITY.md), [changelog](CHANGELOG.md)
- [Open-source principles this repository follows](docs/open-source-principles.md)

Release gates (license text, naming, security contact) are tracked in
[open-questions.md](open-questions.md). The repository must never contain customer data,
account identifiers, private thresholds, credentials, or copied proprietary material.
