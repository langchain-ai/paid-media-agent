# Sandbox and snapshots

Managed Deep Agents gives every durable thread its own LangSmith sandbox as the model's
filesystem and syncs `skills/` (a link to `workspace/skills/`) into it. Local coding-agent skills
in `.agents/skills/` stay outside the sandbox. The repository declares
which image that sandbox starts from and proves the image before a deploy.

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

- `sandbox/__init__.py` declares the Python 3.13 base. MDA automatically bakes `sandbox/setup.sh`
  on deploy/dev, reuses its recipe snapshot, and rebuilds when the script or base changes. The
  recipe installs and verifies Jinja2, WeasyPrint 70 with native libraries, ripgrep, and jq.
  Existing threads keep their sandbox. Preflight requires the declaration and recipe.
- `sandbox/Dockerfile` runs the same recipe for optional standalone publishing. `sandbox publish`
  sends only those two files through the LangSmith SDK and saves the resulting id in `.env`
  and the declaration. `sandbox use` declares an existing snapshot as the bake base.
- Sandbox libraries do not install packages in the separate Agent Server. PDF reports still need
  native libraries in the host image where report tools run. Self-hosted Docker includes them.
- `runtime/sandbox.py` holds only the probe: open a short-lived sandbox, upload the skills, check
  the workspace, render a PDF, verify no key-like environment values, delete it. The per-process
  sandbox backend that mirrored host artifacts into a sandbox lives on the `self-hosted` branch.
- `execute` stays hidden from the model everywhere. Host code uses the sandbox shell only in the
  probe.
