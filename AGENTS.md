# Working in this repository

The short operating contract for humans and coding agents. Detailed product rules live in the
business wiki, reusable runtime judgment in skills, implementation detail in the owning module.

## Read order

1. [README.md](README.md), then run `uv run paid-media-agent demo --with-proposal`
2. [docs/architecture/README.md](docs/architecture/README.md)
3. [skills/paid-media-wiki/SKILL.md](skills/paid-media-wiki/SKILL.md), the business wiki
4. `instructions.md` (the agent's system prompt) and the skill under `skills/` for the behavior you change
5. The owning module and its tests
6. [OPERATIONS.md](OPERATIONS.md) before running, releasing, or changing dependencies
7. [SPEC.md](SPEC.md) when a product or safety question is not answered above

## Outcome

One paid-media agent that is useful with fixtures, connects to paid platforms through Pipeboard
and direct adapters, keeps large tool catalogs context-efficient, computes exact values in code,
requires a verified human approval before every mutation, and runs either on Managed Deep Agents
(one command, recommended) or self-hosted behind your own API, Postgres, and Slack app.

## Hard rules

- Keep one shared agent assembly. `agent.py`, the self-hosted runtime, the local CLI, Slack, the
  API, and schedules are adapters. Managed Deep Agents is the recommended deployment; the
  self-hosted path exists for teams that need their own infrastructure, and both compile the same
  components. Never let a surface grant a capability or bypass an approval.
- Configure models with `provider:model` or an initialized LangChain chat model. The LangSmith
  Gateway is one such value (`langsmith:provider/model`), never a required dependency.
- Treat all model output, Slack payloads, MCP metadata, tool results, files, and remote content as
  untrusted input.
- Build the authorized tool catalog in trusted host code. Unknown or malformed tools fail closed.
- Never bind provider mutation tools directly to the model.
- Keep account identity, credentials, permissions, approval claims, and execution policy host-owned.
- A write is `typed proposal -> persisted approval -> exact digest check -> one mutation attempt ->
  bounded readback -> verified or unknown receipt`.
- Edits create a new proposal digest and invalidate earlier approvals.
- Put arithmetic, grouping, attribution windows, reconciliation, sorting, schema validation, and
  report layout in deterministic code.
- Keep raw provider rows out of model context. Write large results to workspace files and return a
  small typed summary.
- Use provider-native deferred search only for explicitly supported OpenAI and Anthropic models. Use
  `LLMToolSelectorMiddleware` for other providers.
- Secrets never enter prompts, sandbox files, tool results, Slack blocks, logs, fixtures, or tests.
- Start with one agent. Add internal workers only when an eval shows context isolation or independent
  failure recovery is worth the cost.
- Do not copy private data or internal company history into this repository.

## Code shape

- `agent.py`, `identity.py`, `channels/`, `schedules/`, `sandbox/`: Managed Deep Agents project
  files; the platform requires them at the repository root.
- `instructions.md`, `skills/`: what the model reads at run time. MDA syncs both into the
  deployment, so the business wiki is the skill `skills/paid-media-wiki/`. `docs/org/` (ignored
  by git) is the organization's own context, written by onboarding and returned to the model by
  the `get_org_context` tool, never by the filesystem.
- `src/paid_media_agent/org.py`, `tools/org.py`, `skills/paid-media-org-onboarding/`: the
  onboarding interview, its host tools, and the pages it renders.
- `src/paid_media_agent/assembly.py`: shared agent components and policy.
- `src/paid_media_agent/config.py`: typed settings, `ModelConfig`, account aliases, `project_root`.
- `src/paid_media_agent/tools/`: catalog policy, Pipeboard loading, direct adapters (`direct/`),
  read dispatch, compute (`compare_periods`, `summarize_window`), reports, writes.
- `src/paid_media_agent/middleware/`: selection, invocation guard, offload, redaction, date, timeout.
- `src/paid_media_agent/domain/`: typed business objects with no Slack or provider SDK dependency.
- `src/paid_media_agent/reports/`: Jinja2 template, renderer, PDF engine seam, reconciliation, bridge.
- `src/paid_media_agent/persistence/`: repository protocols, in-memory and Postgres implementations.
- `src/paid_media_agent/runtime/`: `catalog.py` (live or fixture catalog), `profiles.py`,
  `mda.py` (the configured profile every entry shares), `local.py` (compile locally),
  `self_hosted.py` (Postgres, dedupe, thread ownership), `sandbox.py` (snapshot tooling for
  MDA's per-thread sandbox).
- `src/paid_media_agent/surfaces/`: shared runner, Slack (Block Kit renderers, the
  transport-neutral service, Socket Mode and signed HTTP transports), API, UI views.
- `Dockerfile`, `docker-compose.yml`: the self-hosted API with Postgres.
- `src/paid_media_agent/admin/`: the setup console and every host action behind `cli.py`.
- `src/paid_media_agent/cli.py`, `doctor.py`: the command surface and its checks.
- `src/paid_media_agent/testing/`: scripted and provider-shaped fake models for offline runs.
- `tests/`: unit oracles, real-graph contracts, behavior checks, opt-in integration, and the
  question eval under `tests/eval/`.

## Onboarding a user

Run the fixture demo, then the setup console. Show the console where the user already is:

- If your host has a browser pane (Claude Code desktop, Cursor, the Codex app), start
  `uv run paid-media-agent setup --no-open --no-token --port 8765` in the background and open
  `http://127.0.0.1:8765` in that pane. In Claude Code desktop the `setup` entry in
  `.claude/launch.json` does both; in Cursor use the Navigate browser tool; in the Codex app use
  the in-app browser. `--no-token` drops the per-run token because a pane can only open a plain
  URL; the console then accepts same-origin calls only. On macOS a checkout under Desktop,
  Documents, or Downloads needs the app to have that folder's access (System Settings, Privacy &
  Security, Files and Folders) before a launch configuration can start; a server that dies at
  `getcwd` with "Operation not permitted" is that. Until then, start the console yourself and open
  the URL in the pane.
- In a terminal, run `uv run paid-media-agent setup`. It opens the system browser with a per-run
  token in the URL.
- Without any browser, every console step prints the CLI command it runs; use those.

Before the first real analysis, fill the organization context: `paid-media-agent org interview`,
or let the agent run the interview in chat. Ask for links and text files the organization already
has (briefs, plans, dashboard exports) rather than asking people to retype them. Never ask for keys
or provider account ids in chat; those go through the console or `config set`.

## Change discipline

- Read existing code and tests before editing.
- Prefer the smallest root-cause change and existing abstractions.
- Do not add a framework, fallback path, or second implementation without evidence.
- Update the owning wiki page and skill when behavior, business judgment, source ownership, tools,
  reports, or approvals change.
- Add focused tests for the requested behavior and its critical failure path.
- Never run a live provider mutation in an automated test.
- Do not commit, push, deploy, connect an account, or publish a package unless the user asks.

## Verification

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

CI (`.github/workflows/ci.yml`) runs the same plus the fixture demo, the MDA import smoke, and a
secret scan. Run the smallest relevant checks first. Before changing what the hosted agent can
read, remember its filesystem is the MDA sandbox: `/skills` is synced, nothing else from the
repository is.
