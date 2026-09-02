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
