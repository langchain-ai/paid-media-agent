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
