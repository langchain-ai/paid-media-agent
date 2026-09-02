# Paid Media Agent

Paid Media Agent is an open-source Deep Agents application for analyzing and safely managing paid
platforms through Pipeboard. One shared agent core powers local development, Managed Deep Agents
(MDA), self-hosted deployments, Slack, and an Agent UI.

A developer should be able to:

- clone the repository and run a useful fixture-backed demo without connecting an ad account;
- choose any supported tool-calling model directly, without a LangSmith Gateway;
- connect Google Ads, Meta Ads, Reddit Ads, and other supported platforms through Pipeboard;
- ask business questions across campaigns, audiences, creatives, spend, conversions, and pipeline;
- generate reconciled reports from deterministic calculations;
- review an exact proposed change before any provider mutation runs;
- deploy the simple Slack experience through MDA or use the rich Slack adapter locally and in a
  self-hosted environment;
- use the same threads, proposals, reports, and receipts from an Agent UI.

## Architecture

The model investigates, chooses evidence, and explains results. Trusted code owns tool authorization,
account identity, arithmetic, validation, reconciliation, approval state, provider mutation, readback,
and report layout.

```text
Slack / Agent UI / API / schedule
              |
       shared agent assembly
              |
  skills + business wiki + middleware
              |
 authorized Pipeboard catalog + deterministic tools
              |
 proposal -> approval -> one mutation -> readback -> receipt
```

Provider-native deferred tool search is used only when the selected OpenAI or Anthropic model supports
it. Other models use `LLMToolSelectorMiddleware`. Both paths finish by resolving the selected name and
schema against the same host-owned authorized catalog.

## Runtime profiles

| Profile | Best for | What it provides |
|---|---|---|
| Local | development and demos | fixture data, local filesystem, local graph, optional Slack Socket Mode |
| MDA | fastest managed deployment | managed threads, checkpoints, sandbox, schedules, observability, and native Slack |
| Self-hosted | full infrastructure and UX control | Postgres-backed state, rich Slack, custom auth, custom API, and optional Agent UI |

The profiles share business logic and tool policy. A surface adapter may render differently, but it
cannot grant a capability or bypass an approval.

## Quick start

```bash
uv sync --all-extras --dev
uv run paid-media-agent demo
```

The demo runs the real Deep Agents graph with a scripted model, a fixture catalog, and synthetic data.
It needs no network and no secrets. It prints a reconciled two-week comparison across three fixture
accounts, cites the analysis and source artifacts written under `workspace/analysis/`, keeps missing
metrics visible as `unavailable`, and suppresses the cross-platform total when a source is incomplete.

```bash
uv run paid-media-agent demo --with-proposal   # adds a governed fake write: propose -> interrupt -> approve -> readback -> receipt
uv run paid-media-agent doctor                 # configuration diagnostics without secret values
uv run paid-media-agent doctor --snapshot      # sandbox snapshot compatibility contract
uv run paid-media-agent serve                  # self-hosted API (self-host extra; Postgres when DATABASE_URL is set)
uv run paid-media-agent slack                  # rich Slack adapter in Socket Mode (slack extra)
mda dev                                        # Managed Deep Agents local run from agent.py
```

To use a real model, copy `.env.example` to `.env`, set `PAID_MEDIA_MODEL` to a `provider:model`
value, and add that provider's key. To read live accounts, add a scoped `PIPEBOARD_API_TOKEN` and map
aliases in `config/accounts.example.toml` (or your own file via `PAID_MEDIA_ACCOUNT_CONFIG_PATH`).
Provider mutations stay globally disabled; the write path runs against an in-memory fake until the
live-write canary is separately authorized.

## What is implemented

| Area | Where | Evidence |
|---|---|---|
| Shared assembly | `src/paid_media_agent/assembly.py` | `tests/contract/test_surfaces_and_runtimes.py` |
| Deny-by-default catalog and invocation guard | `tools/catalog.py`, `tools/reads.py`, `middleware/authorization.py` | `tests/unit/test_catalog_policy.py`, `tests/contract/test_read_path_graph.py` |
| Model capability registry and two selection paths | `middleware/tool_selection.py` | `tests/contract/test_selection_matrix.py` |
| Deterministic comparison and reports | `tools/compute.py`, `reports/` | `tests/unit/test_compute.py`, `tests/unit/test_reads_and_surfaces.py` |
| Governed writes with signed single-use approvals | `tools/writes.py`, `persistence/` | `tests/contract/test_write_flows_graph.py` |
| Live-write gates, kill switch, reviewed policy file | `tools/writes.py` `WriteGate`, `config/write-policy.example.toml` | `tests/contract/test_live_write_gates.py`, `tests/unit/test_write_policy_and_gate.py` |
| Slack (native, Socket Mode, signed HTTP), API, UI views | `agent.py`, `channels/slack.py`, `surfaces/` | `tests/contract/test_surfaces_and_runtimes.py` |

PDF rendering needs WeasyPrint's native libraries (Pango, Cairo). Without them the report renders as
HTML and `doctor` says so; nothing else changes.

## Writes

Changes are proposals, never direct calls. `discover_write_operations` lists the admitted operations
from the reviewed policy file (`config/write-policy.example.toml`, validated against the current
catalog at startup). `propose_change` reads the current value, derives risk flags, and persists a
digest-bound ChangeSet. `execute_change` pauses the graph; only a host-created, signed, single-use
approval lets the executor run one mutation attempt followed by bounded readback.

Live provider mutations stay off. With a live catalog the runtime builds the exact Pipeboard write
adapter, but the executor refuses it unless the operator clears every gate in
[docs/operations/live-write-runbook.md](docs/operations/live-write-runbook.md): no kill-switch file,
`PAID_MEDIA_WRITES_ENABLED=true`, a pinned reviewed catalog revision, and an explicit canary tool
allowlist. Automated tests never set those values.

## Managed Deep Agents path

`agent.py` exports the definition MDA needs; `instructions.md`, `skills/`, and `channels/slack.py`
are the managed project files. With a LangSmith API key in `.env`:

```bash
uv run mda dev        # local managed run with LangSmith Studio
uv run mda deploy .   # hosted deployment; provisions native Slack from channels/slack.py
```

Native Slack supports approve and reject on `execute_change`. Use the rich adapter
(`paid-media-agent slack`) when reviewers need edits, receipts, and files in Block Kit.

## Release status

The first tagged release is gated on the items in [open-questions.md](open-questions.md). The
repository ships under the [Apache-2.0 license](LICENSE) as the recommended default pending
maintainer approval, with a [security policy](SECURITY.md), [contributing guide](CONTRIBUTING.md),
[changelog](CHANGELOG.md), and CI that runs the offline suite, the fixture demo, and a secret scan.

## Start here

- [Product and engineering specification](SPEC.md)
- [Implementation prompt for Claude Fable 5.1](IMPLEMENTATION_PROMPT.md)
- [Architecture index](docs/architecture/README.md)
- [Paid-media business context](docs/business-context/README.md)
- [Source inventory](prep/source-inventory.md)
- [Operating contract](AGENTS.md)
- [Live-write canary runbook](docs/operations/live-write-runbook.md)
- [Examples](examples/README.md) and [migration notes](docs/migration.md)

## Public-release boundary

The repository must not contain customer data, company-specific account identifiers, private
thresholds, production history, credentials, internal Slack or Notion links, or copied proprietary
fixtures. The license, trademark wording, and maintainer security contact are explicit release gates
in [open-questions.md](open-questions.md).

