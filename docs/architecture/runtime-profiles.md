# Runtime profiles

## Shared assembly

`build_agent_components` is the center. It receives typed settings, a runtime profile, and an
authorized tool catalog. It returns the model, tools, middleware, and interrupt policy. It performs
no network calls and stores no process-global mutable state.

## One configured profile

`runtime/mda.py::configured_profile` resolves what a process runs: the live Pipeboard catalog and
direct adapters when their credentials exist, the fixture catalog otherwise; the reviewed write
policy validated against that catalog; the approval policy from `PAID_MEDIA_APPROVER_IDS`. Two
callers compile it:

- `agent.py` hands the components to `define_deep_agent`. Managed Deep Agents supplies the
  checkpointer, the per-thread sandbox, identity, schedules, and Slack.
- `runtime/local.py::build_configured_runtime` compiles the same components with
  `create_deep_agent`, the repository as the model's filesystem, and an in-memory checkpointer,
  for `paid-media-agent ask`, `report`, and the console's "Try it".

`build_local_runtime` is the fixture-only variant that takes an injected model: the demo and the
test suite.

## What the model can read

In the deployment the model's filesystem is the MDA sandbox: `/skills` (synced by MDA, the wiki
included as `skills/paid-media-wiki/`) and `/workspace` (the thread's scratch space). Nothing else
from the repository is present. Every other input reaches the model through host tools: the
organization profile through `get_org_context`, artifacts through their ids, files through
`render_report`. Locally the repository is the filesystem, with writes allowed only under
`/workspace`, and the same tools are used, so a prompt or skill never names a path that exists in
only one world.

## Parity contract

For the same model, catalog, thread state, and user request, the deployment and the local CLI
expose the same authorized capabilities and terminal domain objects. Timing, trace metadata, and
presentation may differ. Capability and approval policy may not.

## Self-hosting

The self-hosted profile (Postgres, FastAPI boundary, rich Slack transports, per-process sandbox
backend, LangGraph Server factory) lives on the `self-hosted` branch. See
[docs/self-hosting.md](../self-hosting.md).

## Implementation notes (2026-09-08)

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
