# Sandbox

Managed Deep Agents gives every thread its own sandbox as the model's filesystem and syncs
`skills/` into it. This directory declares which image that sandbox starts from.

The default declaration uses Python 3.13. `mda deploy` and `mda dev` automatically bake
`setup.sh` into a reusable snapshot. The recipe installs ripgrep, jq, Jinja2, and WeasyPrint
70 with Pango, Cairo, and fonts, and fails the build if PDF rendering does not work.
No separate publish step or local Docker is needed. A recipe or base change creates a new
snapshot; existing conversations keep their current sandbox.

The recipe never writes project data or credentials into the image. Dependencies are declared
once in `setup.sh`; the optional `Dockerfile` runs the same script for standalone publishing:

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # build + declare
uv run paid-media-agent sandbox use <existing-snapshot-id>                # declare only
uv run paid-media-agent sandbox test                                      # open a probe sandbox, check, delete
```

`publish` and `use` replace the default base in `sandbox/__init__.py` with a literal snapshot
reference and write the same id to `.env` for `sandbox test`. MDA still applies `setup.sh` to
that base. Keep both `__init__.py` and `setup.sh`: the deployment preflight checks for them.

`test` proves the snapshot can host the agent: Python, uploaded skills and wiki pages, the
`/workspace` layout, a PDF rendered inside the sandbox, and no key-like environment values.
It tests the explicitly published snapshot, not MDA's deployment-owned recipe snapshot.

Sandbox libraries do not install packages into the Agent Server. Report tools currently render
on that host, where PDF still requires native libraries. Self-hosted Docker includes them.

See [MDA sandbox lifecycle](https://docs.langchain.com/langsmith/python/managed-deep-agents-sandboxes).
