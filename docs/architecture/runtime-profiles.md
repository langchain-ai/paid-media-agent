# Runtime profiles

## Shared assembly

`build_agent_components` is the center. It receives typed settings, a runtime profile, and an
authorized tool catalog. It returns the model, tools, middleware, and interrupt policy. It performs
no network calls and stores no process-global mutable state.

## One configured profile

`runtime/mda.py::configured_profile` resolves the catalog, reviewed write policy, and approval
policy from `PAID_MEDIA_APPROVER_IDS`. `PAID_MEDIA_DATA_MODE=sample` uses only fixtures; `live`
requires connected providers and excludes synthetic platforms. The default `auto` mode selects
providers from configured credentials and otherwise uses fixtures. Three callers compile it:

- `agent.py` hands the components to `define_deep_agent`. Managed Deep Agents supplies the
  checkpointer, the per-thread sandbox, identity, schedules, and Slack. This is the recommended
  deployment.
- `runtime/self_hosted.py::build_self_hosted_runtime` compiles the same components with
  `create_deep_agent` behind the FastAPI boundary and the Slack adapter, with proposals,
  claims, receipts, dedupe, thread ownership, and checkpoints in Postgres when `DATABASE_URL` is
  set and in memory otherwise.
- `runtime/local.py::build_configured_runtime` compiles them with an in-memory checkpointer for
  `paid-media-agent ask` and `report`.

`build_local_runtime` is the fixture-only variant that takes an injected model: the demo and the
test suite.

## What the model can read

In the deployment the model's filesystem is the MDA sandbox: `/skills` (synced by MDA, the wiki
included as `skills/paid-media-wiki/`) and `/workspace` (the thread's scratch space). The checkout's
`skills/` is a relative link to `workspace/skills/`. Local coding-agent skills in `.agents/skills/`
are not synced to the sandbox. Business context belongs in
`workspace/skills/company-context/`, alongside the runtime skills. Original briefs remain in
`workspace/sources/` and are not synced. See [customization](../customization.md).

Locally the repository is the filesystem. Writes are allowed under `/workspace` except
`workspace/skills`, which stays read-only. Coding-agent files, raw sources, and secret paths are denied. Provider reads and report generation use the same
host tools in both runtimes.

## Parity contract

For the same model, catalog, thread state, and user request, the deployment and the local CLI
expose the same authorized capabilities and terminal domain objects. Timing, trace metadata, and
presentation may differ. Capability and approval policy may not.

## Self-hosting

The self-hosted profile is the same assembly with durable state you own. It reads the same
runtime skills and company context, with the local filesystem permissions described above. See
[docs/self-hosting.md](../self-hosting.md).

| Profile | Main advantage | Main cost or limit |
|---|---|---|
| MDA | one command, managed threads, sandbox, schedules, identity, Slack | generic approval card, US region, in-memory proposal state per process |
| Self-hosted | your data, auth, Slack cards with edits, Postgres durability | you run the API, database, Slack app, upgrades, and backups |

## Runtime components

- `runtime/profiles.py` defines `RuntimeProfile`: artifacts, accounts, catalog provider, read and
  write providers, write policy, approval policy, signer, repositories, and run mode.
- `runtime/catalog.py::load_catalog` applies the admitted names from the write-policy file to the
  local policy before the live catalog is classified, so the catalog, the policy, and the gate
  agree on one reviewed set. With a live catalog the profile uses `PipeboardReadProvider` and the
  gated `PipeboardWriteProvider` and marks the provider as not fake; the fixture fake is used only
  with the fixture catalog, so a production receipt can never come from a fake.
- `runtime/local.py::compile_graph` uses a `FilesystemBackend` rooted at the checkout, skills from
  `/skills/`, and permissions that deny `.env`, `.venv`, `.git`, `.mda`, and any write outside
  `/workspace/`.
- `connectors/mcp.py` is intentionally absent: MDA's MCP connector would bind provider tools to the
  model directly, bypassing the authorized catalog. Tools always enter through the assembly.
