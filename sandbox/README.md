# Sandbox

Managed Deep Agents gives every thread its own sandbox as the model's filesystem and syncs
`skills/` into it. This directory declares which image that sandbox starts from.

`Dockerfile` is the optional reproducible image: Python 3.13, ripgrep, jq, WeasyPrint with its
native libraries, and Jinja2. It copies no instructions, skills, or secrets. There is no local
container; LangSmith builds the image and runs the sandbox.

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # build + declare
uv run paid-media-agent sandbox use <existing-snapshot-id>                # declare only
uv run paid-media-agent sandbox test                                      # open a probe sandbox, check, delete
```

`publish` and `use` generate `sandbox/__init__.py` (read statically by Managed Deep Agents, which
only accepts a literal) and write the same snapshot id to `.env` for `sandbox test`. `mda check`
reports when the two disagree. Without `sandbox/__init__.py`, MDA uses its default image, which is
enough for reads, analysis, HTML reports, and governed writes.

`test` proves the snapshot can host the agent: Python, uploaded skills and wiki pages, the
`/workspace` layout, a PDF rendered inside the sandbox, and no key-like environment values.
