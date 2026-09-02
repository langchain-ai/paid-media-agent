# Working in this repository

This file is the short operating contract for humans and coding agents. Keep it small. Put detailed
product rules in the business wiki, reusable runtime judgment in skills, and implementation detail in
the owning module.

## Read order

1. [README.md](README.md)
2. [SPEC.md](SPEC.md)
3. [docs/architecture/README.md](docs/architecture/README.md)
4. [docs/business-context/README.md](docs/business-context/README.md)
5. The owning module, test, and skill for the change
6. [OPERATIONS.md](OPERATIONS.md) before running, releasing, or changing dependencies

## Outcome

Build one portable paid-media agent that is useful with fixtures, connects to paid platforms through
Pipeboard, keeps large tool catalogs context-efficient, computes exact values in code, and requires a
verified human approval before every mutation.

## Hard rules

- Keep one shared agent assembly. MDA, self-hosted, Slack, UI, and schedules are adapters.
- Configure models directly with `provider:model` or an initialized LangChain chat model. Do not add
  a LangSmith Gateway dependency.
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

- `agent.py`: MDA entry only. `channels/slack.py` declares native Slack; `sandbox/` holds the snapshot recipe.
- `src/paid_media_agent/assembly.py`: shared agent components and policy.
- `src/paid_media_agent/config.py`: typed settings, `ModelConfig`, and host-owned account aliases.
- `src/paid_media_agent/tools/`: catalog policy, Pipeboard loading, read dispatch, compute, reports, writes.
- `src/paid_media_agent/middleware/`: model-aware selection, invocation guard, offload, and redaction.
- `src/paid_media_agent/domain/`: typed business objects with no Slack or provider SDK dependency.
- `src/paid_media_agent/reports/`: Jinja2 template, renderer, reconciliation, and artifact bridge.
- `src/paid_media_agent/persistence/`: repository protocols, in-memory and Postgres implementations.
- `src/paid_media_agent/runtime/`: local, MDA, and self-hosted profiles over the one assembly.
- `src/paid_media_agent/surfaces/`: shared runner, Slack (blocks, service, two transports), API, UI views.
- `src/paid_media_agent/testing/`: scripted and provider-shaped fake models for offline runs.
- `skills/`: progressive runtime playbooks.
- `docs/business-context/`: public paid-media doctrine and source boundaries.
- `tests/`: unit oracles, real-graph contracts, opt-in integration, and source-blind evals.

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
uv run mypy src
uv run pytest -q
```

Run the smallest relevant checks first. Before release, also run fixture E2E, approval tamper tests,
context-budget checks, secret scanning, link checking, and both runtime-profile smoke tests described
in [SPEC.md](SPEC.md).

