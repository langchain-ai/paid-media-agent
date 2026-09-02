# Sandbox and snapshots

The project supports two safe paths:

1. build the included reproducible snapshot recipe;
2. reuse an existing snapshot that passes the repository compatibility check.

## Snapshot contents

Bake stable system dependencies and expensive binary packages into the image:

- a supported Python runtime;
- `rg`, `jq`, and basic shell tools;
- report-rendering native libraries;
- optional data tools such as DuckDB and Pandas when the deterministic compute layer uses them;
- image and document inspection libraries required by shipped skills.

Do not bake instructions, skills, business wiki pages, report templates, user data, credentials, or
environment files. Those remain mounted project content or deployment secrets.

## Compatibility contract

`paid-media-agent doctor --snapshot` must check:

- Python and binary versions;
- importability of required packages;
- workspace read/write permissions;
- denial of paths outside the workspace;
- absence of secret environment values from the sandbox;
- outbound network policy;
- deterministic report rendering;
- artifact handoff to the host.

A named snapshot is reusable only while it passes this contract. Snapshot identity alone is not proof
of compatibility.

## Network and artifacts

Provider and Pipeboard requests execute in host tools, not agent-authored sandbox code. Outbound
sandbox network is denied by default and opened only for a documented skill need. Artifact delivery
validates normalized paths, file type, size, and ownership before moving bytes to Slack or the API.

## Implementation notes (2026-09-01)

- `sandbox/Dockerfile` is the reproducible recipe (Python 3.13, ripgrep, jq, WeasyPrint native
  libraries, locked dependencies). It copies no instructions, skills, wiki, or secrets.
- `sandbox/__init__.py` declares an MDA sandbox only when `PAID_MEDIA_SANDBOX_SNAPSHOT` names a
  snapshot that passed `paid-media-agent doctor --snapshot`.
- The checker verifies Python, `rg`/`jq`, required imports, workspace writability, absence of secret
  environment values, home SSH readability, and report rendering. Outbound network policy is enforced
  by the sandbox runtime and reported as unverifiable from inside.
