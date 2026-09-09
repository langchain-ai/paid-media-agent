# Sandbox and snapshots

Managed Deep Agents gives every durable thread its own LangSmith sandbox as the model's
filesystem and syncs `skills/` into it. The repository declares which image that sandbox starts
from and proves the image before a deploy.

## Snapshot contents

Bake stable system dependencies and expensive binary packages into the image:

- a supported Python runtime;
- `rg`, `jq`, and basic shell tools;
- report-rendering native libraries (WeasyPrint with Pango and Cairo);
- optional data tools when the deterministic compute layer uses them.

Do not bake instructions, skills, wiki pages, report templates, user data, credentials, or
environment files. Skills are synced by MDA; everything else reaches the model through host tools.

## Compatibility contract

`paid-media-agent doctor --snapshot` (inside an image) and `paid-media-agent sandbox test`
(against a snapshot) check Python and binary versions, importability of required packages,
workspace read and write permissions, absence of secret environment values, a PDF rendered inside
the sandbox, and that outbound network policy is the platform's, not the image's. A named
snapshot is reusable only while it passes; snapshot identity alone is not proof of compatibility.

## Network and artifacts

Provider and Pipeboard requests execute in host tools, not agent-authored sandbox code. The probe
sandbox is created with default-deny egress. Artifact delivery validates normalized paths, file
type, size, and ownership before moving bytes anywhere.

## Implementation notes (2026-09-08)

- `sandbox/Dockerfile` is the optional reproducible image. `paid-media-agent sandbox publish`
  builds it through the LangSmith SDK (no local Docker) and generates `sandbox/__init__.py`, the
  literal `define_sandbox(snapshot_id=...)` declaration MDA evaluates statically; `sandbox use`
  declares an existing snapshot. Snapshots built from a Dockerfile resolve by id.
- Without `sandbox/__init__.py` MDA uses its default image, enough for reads, analysis, governed
  writes, and HTML reports. PDF rendering in the deployment needs the native libraries in the
  image the host tools run in, which is an open question for the platform.
- `runtime/sandbox.py` holds only the probe: open a short-lived sandbox, upload the skills, check
  the workspace, render a PDF, verify no key-like environment values, delete it. The per-process
  sandbox backend that mirrored host artifacts into a sandbox lives on the `self-hosted` branch.
- `execute` stays hidden from the model everywhere. Host code uses the sandbox shell only in the
  probe.
