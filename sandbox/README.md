# Sandbox

`Dockerfile` is the reproducible recipe for the model's filesystem in production: Python 3.13,
ripgrep, jq, WeasyPrint with its native libraries, and Jinja2. It copies no instructions,
skills, wiki content, or secrets; those are uploaded when a sandbox opens.

There is no local container. LangSmith builds the image and runs the sandbox; `mda dev`,
`langgraph dev`, `serve`, and the console all talk to the same remote sandbox when
`PAID_MEDIA_BACKEND=sandbox`.

```bash
uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox   # build + declare
uv run paid-media-agent sandbox use <existing-snapshot-name>              # declare only
uv run paid-media-agent sandbox test                                      # open, probe, delete
uv run paid-media-agent config set PAID_MEDIA_BACKEND=sandbox
```

`publish` and `use` write the snapshot name to `.env` (read by our runtimes) and generate
`sandbox/__init__.py` (read statically by Managed Deep Agents, which only accepts a literal).
`mda check` reports when the two disagree. Without `sandbox/__init__.py`, MDA runs the agent
without a sandbox, which is enough for reads, analysis, HTML reports, and governed writes.

`test` proves the snapshot can host the agent: Python, uploaded skills and wiki pages, the
`/workspace` layout, a PDF rendered inside the sandbox, and no key-like environment values.
