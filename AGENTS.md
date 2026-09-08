# Working in this repository

The short operating contract for humans and coding agents. Detailed product rules live in the
business wiki, reusable runtime judgment in skills, implementation detail in the owning module.

## Read order

1. [README.md](README.md), then run `uv run paid-media-agent demo --with-proposal`
2. [docs/architecture/README.md](docs/architecture/README.md)
3. [docs/business-context/README.md](docs/business-context/README.md)
4. `instructions.md` (the agent's system prompt) and the skill under `skills/` for the behavior you change
5. The owning module and its tests
6. [OPERATIONS.md](OPERATIONS.md) before running, releasing, or changing dependencies
7. [SPEC.md](SPEC.md) when a product or safety question is not answered above

## Outcome

One portable paid-media agent that is useful with fixtures, connects to paid platforms through
Pipeboard and direct adapters, keeps large tool catalogs context-efficient, computes exact values in
code, and requires a verified human approval before every mutation.

## Hard rules

- Keep one shared agent assembly. MDA, self-hosted, Slack, UI, and schedules are adapters.
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

- `agent.py`, `identity.py`, `channels/`, `schedules/`, `sandbox/`, `langgraph.json`: Managed Deep
  Agents and LangGraph project files; the platform requires them at the repository root.
- `instructions.md`, `skills/`, `docs/business-context/`: what the model reads at run time;
  `docs/org/` (ignored by git) is the organization's own context, written by onboarding.
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
- `src/paid_media_agent/runtime/`: local, MDA, self-hosted profiles; `graph.py` for LangGraph
  Server; `sandbox.py` for the LangSmith sandbox backend.
- `src/paid_media_agent/surfaces/`: shared runner, Slack (blocks, service, Socket Mode and signed
  HTTP transports), API, UI views.
- `src/paid_media_agent/admin/`: the setup console and every host action behind `cli.py`.
- `src/paid_media_agent/cli.py`, `doctor.py`: the command surface and its checks.
- `src/paid_media_agent/testing/`: scripted and provider-shaped fake models for offline runs.
- `tests/`: unit oracles, real-graph contracts, behavior checks, opt-in integration, and the
  question eval under `tests/eval/`.

## Onboarding a user

Run the fixture demo, then `paid-media-agent setup` (or the CLI equivalents it prints). Before the
first real analysis, fill the organization context: `paid-media-agent org interview`, or let the
agent run the interview in chat. Ask for links and text files the organization already has (briefs,
plans, dashboard exports) rather than asking people to retype them. Never ask for keys or provider
account ids in chat; those go through the console or `config set`.

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
secret scan. Run the smallest relevant checks first.
