# Self-hosting

Managed Deep Agents is the one-command path and the recommended one. Self-hosting is for teams
that want the agent behind their own API, database, and Slack app. It is the same agent: the
components `agent.py` hands to MDA, compiled with `create_deep_agent`, with durable state in
Postgres and a small authenticated boundary. Expect a few more steps than `mda deploy .`, not a
different product.

## What you get

- `paid-media-agent serve`: a FastAPI boundary with health, thread messages, proposal read,
  approve, edit, reject, and artifact download, behind bearer tokens mapped to caller names.
- Postgres persistence for checkpoints, proposals, approval claims, receipts, dedupe keys, and
  thread ownership (`DATABASE_URL`), with in-memory state as the fallback for trying things out.
- The rich Slack adapter: Block Kit review cards with Approve, Edit, and Reject, edits typed in
  the thread, receipts, and report files, over Socket Mode (`paid-media-agent slack`) or signed
  HTTP events mounted on the API (`SLACK_TRANSPORT=http`).
- A Docker image with the PDF libraries and a compose file that brings up the API and Postgres.

## Fastest route

```bash
cp .env.example .env                       # add a model key
uv run paid-media-agent config generate PAID_MEDIA_API_TOKENS PAID_MEDIA_APPROVAL_SIGNING_KEY
docker compose up                          # API on :8080, Postgres alongside
curl -s localhost:8080/health
```

`config generate` prints the API token once; clients send the part before `:operator` as the
bearer. Compose sets `DATABASE_URL` for the API container and reads everything else from your
`.env`. The image copies no env file.

Compose mounts `docs/org/` from the checkout into the API container. Business context saved
by your coding agent or `uv run paid-media-agent org interview` is available immediately and
survives container replacement. If you run the image without Compose, mount that folder at
`/app/docs/org` yourself.

## Slack

1. Create a Slack app from `config/slack-manifest.example.yaml` and install it to the workspace.
2. In **OAuth & Permissions**, install the app to your workspace and copy the **Bot User OAuth
   Token** (`xoxb-`). In **Basic Information → App-Level Tokens → Generate Token and Scopes**,
   add `connections:write` and copy the app-level token (`xapp-`). Enable **Socket Mode**.
   Store the tokens: `uv run paid-media-agent config set SLACK_BOT_TOKEN=xoxb-... SLACK_APP_TOKEN=xapp-...`
   (Socket Mode, no public URL). For a hosted deployment set `SLACK_TRANSPORT=http` and
   `SLACK_SIGNING_SECRET`, and point the app's request URL at `/slack/events` on your API.
3. Name the approvers: `PAID_MEDIA_APPROVER_IDS=slack:<team_id>:<user_id>,...`. The requester
   cannot approve their own change unless `PAID_MEDIA_ALLOW_SELF_APPROVAL=true`.
4. `uv run paid-media-agent test slack`, then `uv run paid-media-agent slack`.

Mention the app in a channel or DM it. A proposed change arrives as a card; Approve records a
signed, single-use claim for that revision, Edit asks for `edit <field> <value>` in the thread and
produces a new revision, Reject ends it. The receipt says verified, failed, or unknown.

## Without Docker

```bash
uv sync --all-extras --dev
uv run paid-media-agent config set DATABASE_URL=postgresql://...   # or leave empty for in-memory
uv run paid-media-agent test db
uv run paid-media-agent serve --port 8080
```

The console (`uv run paid-media-agent setup`, step "Self-host") runs the same actions with
buttons and shows each command it runs.

## Boundaries that do not change

Self-hosting changes where the agent runs, not what it may do. The authorized catalog, account
aliases, write policy, approval claims, one mutation attempt, and bounded readback are the same
code as in the managed deployment. The API cannot approve a change for a caller who is not in
`PAID_MEDIA_APPROVER_IDS`, and no surface can execute a mutation outside `execute_change`.

## History

Between 2026-09-08 and 2026-09-09 `main` was Managed Deep Agents only and this path lived on the
`self-hosted` branch (frozen at `a5477d9`). It is back on `main`; that branch is history.
