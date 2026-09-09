# Self-hosting

`main` is Managed Deep Agents only. Managed Deep Agents (MDA) runs the agent: threads,
checkpoints, a sandbox per thread, the weekly and monthly schedules, caller identity, and Slack.
The repository holds the agent (instructions, skills, wiki, tools, policy) and a local console
and CLI for onboarding; it does not ship a server of its own.

The self-hosted path that existed before this cut lives on the
[`self-hosted` branch](https://github.com/amal-irgashev/paid-media-agent-open-source/tree/self-hosted),
frozen at commit `a5477d9`. It compiles the same components with `create_deep_agent` and adds:

- `paid-media-agent serve`: a small authenticated FastAPI boundary (threads, proposals,
  approve/edit/reject, artifacts, health) with bearer tokens mapped to caller refs;
- Postgres persistence for checkpoints, proposals, approval claims, receipts, and dedupe
  (`DATABASE_URL`), with in-memory state as the fallback;
- the rich Slack adapter over Socket Mode (`paid-media-agent slack`) or signed HTTP events,
  with Block Kit review cards, edits in the thread, receipts, and file delivery;
- `PAID_MEDIA_BACKEND=sandbox`: a LangSmith sandbox per process as the model's filesystem, with
  host artifacts mirrored in and PDFs rendered inside;
- `langgraph.json` and a graph factory for a local LangGraph Server and Studio;
- `Dockerfile` and `docker-compose.yml` for the API with Postgres.

## Why the cut

One deployment path is simpler to onboard, test, and support. MDA already provides what the
self-hosted profile reimplemented, and the pieces that differ (Block Kit cards, edits from Slack,
durable state) are better raised with the platform than maintained twice. The branch stays so
nobody has to rebuild it if a self-hosted requirement returns.

## What stayed on main for a custom Slack channel

`surfaces/slack/blocks.py` (Block Kit renderers for proposals, receipts, reports, answers),
`surfaces/slack/service.py` (the transport-neutral event and action service), and
`surfaces/runner.py` (send, resume, approve, reject, edit over the graph) remain and are tested.
A custom channel would supply only the transport.

## Using the branch

```bash
git fetch origin self-hosted
git switch self-hosted
uv sync --all-extras --dev
uv run paid-media-agent doctor
uv run paid-media-agent serve            # or: docker compose up
```

The branch keeps its own README and OPERATIONS with the full command reference. It does not
receive new features; security fixes to shared modules can be cherry-picked from `main`.
