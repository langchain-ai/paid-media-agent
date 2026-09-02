# Sandbox snapshot

`Dockerfile` is the reproducible recipe: Python 3.13, ripgrep, jq, WeasyPrint native libraries,
and the locked dependencies. It contains no instructions, skills, wiki content, or secrets.

```bash
docker build -f sandbox/Dockerfile -t paid-media-agent-sandbox .
docker run --rm paid-media-agent-sandbox
```

To reuse an existing snapshot, run the compatibility contract inside it:

```bash
uv run paid-media-agent doctor --snapshot
```

A snapshot is reusable only while that check passes. For MDA, set `PAID_MEDIA_SANDBOX_SNAPSHOT`
to the snapshot name so `sandbox/__init__.py` declares it.

## Managed Deep Agents

MDA requires `sandbox/__init__.py` to export a named `sandbox` when the file exists, so the
declaration is opt-in: copy `sandbox/example_sandbox.py` to `sandbox/__init__.py` after the
snapshot is published. Without it, `mda deploy` runs the agent without a sandbox, which is enough
for reads, analysis, reports, and governed writes, since provider calls stay host-side.
