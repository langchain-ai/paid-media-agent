# Contributing

Read [AGENTS.md](AGENTS.md) first; it is the operating contract for humans and coding agents.

## Setup

```bash
uv sync --all-extras --dev
uv run paid-media-agent demo
```

## Optional named local URL

[Portless](https://github.com/vercel-labs/portless) gives the setup console a stable URL and
assigns its port automatically. Portless requires Node.js 24+. It is optional; the regular Python
setup command needs no Node.js.

```bash
npm install -g portless
portless paid-media uv run paid-media-agent setup
```

The console opens at `https://paid-media.localhost` with its usual per-run token. Portless handles
the local proxy and HTTPS certificate; its first run may ask for certificate trust and administrator
access. The console stays bound to loopback and accepts only the exact `.localhost` hostname
Portless provides. Custom domains, LAN mode, and public tunnels are not supported for this console.

To use plain HTTP on an unprivileged port instead:

```bash
PORTLESS_HTTPS=0 PORTLESS_PORT=1355 portless paid-media uv run paid-media-agent setup
```

This opens `http://paid-media.localhost:1355`. Use `--no-open --no-token` after `setup` when a
coding agent opens the console in its browser pane. Default onboarding remains
`uv run paid-media-agent setup` at `http://127.0.0.1:8765`.

## Before opening a pull request

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

The suite is offline by design. Live checks are opt-in (`PAID_MEDIA_LIVE_TESTS=1`) and read-only.

## Rules that reviews enforce

- One shared assembly. Surfaces and runtimes adapt; they do not fork tools, prompts, or policy.
- Deny by default. A new provider tool needs `readOnlyHint` metadata and, for mutations, a reviewed
  row in the write-policy file plus a canary before it is reachable.
- Arithmetic, grouping, thresholds, digests, permissions, and layout live in code with tests.
  Model prose never carries a number that code did not produce.
- Missing data stays missing. Do not convert unavailable metrics to zero.
- Every governed-write change ships with the real-graph rejection tests it needs.
- No customer data, account identifiers, private thresholds, or internal links in the repository.
- Update the owning architecture page, wiki page, and skill in the same change, and
  append to `log.md`.

## Commit and pull request hygiene

- Small, root-cause changes over stacked patches.
- Explain what the change makes true and which test proves it.
- Do not weaken assertions or widen tolerances to make a test pass.

## Local hooks and shortcuts

```bash
uv tool install pre-commit && pre-commit install   # the CI lint and format gates, before each commit
make check                                          # lint, format check, types, tests (what CI runs)
make demo                                           # the fixture demo
```

Commit messages follow the plain imperative ("Add X", "Fix Y"); `CHANGELOG.md` gets one line per
user-visible change under Unreleased. Releases are tags (`vX.Y.Z`); the release workflow builds the
artifacts and publishes the changelog section as the release notes.
