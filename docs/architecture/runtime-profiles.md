# Runtime profiles

## Shared assembly

`build_agent_components` is the center. It receives typed settings, a runtime profile, and an
authorized tool catalog. It returns the model, tools, middleware, interrupt policy, and response
schema. It performs no network calls and stores no process-global mutable state.

## Local

Local mode is the default development path. It uses fixtures and an in-memory checkpointer for tests.
Developers may opt into live read-only Pipeboard calls. Slack uses Socket Mode when configured.

Local mode is not a production persistence profile. Restart recovery tests use a persistent test
store or Postgres container.

## Managed Deep Agents

The root `agent.py` exports one named MDA agent. MDA project files configure instructions, skills,
connectors, sandbox, schedules, identity, memory, and native Slack. MDA is optional. It simplifies
operations but does not own the product's tools, business rules, or approval contracts.

The native Slack channel is the simple managed surface. Use the external rich Slack adapter when
Block Kit review, streamed progress, files, edited proposals, or custom receipts are required.

## Self-hosted

The self-hosted profile compiles the same components with `create_deep_agent`. Postgres owns
checkpoints, store data, proposals, approval claims, receipts, and dedupe records. FastAPI exposes a
small authenticated boundary. Slack can use Socket Mode or signed HTTP events.

Agent UI support depends on an Agent Server-compatible endpoint. Protocol compatibility is an adapter;
it must not fork graph behavior.

## Parity contract

For the same model, fixture catalog, thread state, and user request, every profile must expose the same
authorized domain capabilities and terminal domain objects. Timing, trace metadata, and presentation
may differ. Capability and approval policy may not.

## Tradeoffs

| Profile | Main advantage | Main cost or limit |
|---|---|---|
| Local | fastest development and no hosted runtime dependency | not a durable production setup |
| MDA | smallest production operations burden and native Slack | managed public beta, current US-region boundary, simpler Slack UX |
| Self-hosted | full control over data, auth, Slack, persistence, and deployment | the operator owns uptime, upgrades, backups, security, and incident response |

MDA is a deployment option, not a product dependency. Self-hosting does not require an MDA or
LangSmith account when the operator uses the custom graph/API profile. A separate LangSmith or Agent
Server deployment may be supported as another adapter under its own current licensing and service
terms.

## Implementation notes (2026-09-01)

- `runtime/profiles.py` defines `RuntimeProfile`: artifacts, accounts, catalog provider, read and
  write providers, write policy, approval policy, signer, repositories, and run mode.
- `runtime/local.py` compiles the components with `create_deep_agent`, a `FilesystemBackend` rooted
  at the checkout, skills from `/skills/`, and permissions that deny `.env`, `.venv`, `.git`, and any
  write outside `/workspace/`.
- `runtime/self_hosted.py` reuses `compile_graph`, switches repositories and the checkpointer to
  Postgres when `DATABASE_URL` is set, and loads the live catalog when a Pipeboard token exists.
- `agent.py` calls `runtime/mda.py`, which builds the same components; MDA supplies the backend,
  checkpointer, store, instructions, and skills. The live catalog is loaded at import only when a
  token is configured; otherwise the fixture catalog is used.
- `connectors/mcp.py` is intentionally absent: MDA's MCP connector would bind provider tools to the
  model directly, bypassing the authorized catalog. Tools always enter through the assembly.

## Live-catalog notes

- With a live catalog, `self_hosted` and `mda` profiles use `PipeboardReadProvider` and the gated
  `PipeboardWriteProvider` and mark the provider as not fake. The fixture fake is used only with the
  fixture catalog, so a production receipt can never come from a fake.
- `load_catalog` applies the admitted names from the write-policy file to `LocalPolicy` before the
  live catalog is classified, so the catalog, the policy, and the gate agree on one reviewed set.
