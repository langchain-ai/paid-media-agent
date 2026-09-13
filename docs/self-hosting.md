# Self-hosting

Run the paid-media agent on your own infrastructure with Docker, Postgres, and an optional Slack
app. MDA remains the shortest hosted path. Both use the same agent tools and approval policy.

## Start the API

```bash
cp .env.example .env
uv run paid-media-agent config generate PAID_MEDIA_API_TOKENS PAID_MEDIA_APPROVAL_SIGNING_KEY
# Add your model key and connect accounts with the setup console or CLI.
docker compose up --build -d
curl http://localhost:8080/health
```

`config generate` prints the API token once. Send the part before `:operator` as a bearer token.
The API listens on localhost. Postgres stores conversations and approvals; a Docker volume stores
report files. Your local `config/` and `workspace/skills/` folders are mounted read-only, so account
mappings, write policy, and business context are available in both containers.

Give your coding agent the [onboarding skill](../.agents/skills/paid-media-onboarding/SKILL.md), or
follow [customization](customization.md) to edit business context and skills manually.

## Connect Slack

1. Create an app from [the Slack manifest](../config/slack-manifest.example.yaml). It enables the
   Agent messaging experience, mentions, and direct messages.
2. In **OAuth & Permissions**, install it to your workspace and copy the **Bot User OAuth Token**
   (`xoxb-`) into `SLACK_BOT_TOKEN` in your local `.env`.
3. In **Basic Information → App-Level Tokens → Generate Token and Scopes**, add
   `connections:write`. Save the `xapp-` token as `SLACK_APP_TOKEN` and enable **Socket Mode**.
4. Start the Slack worker alongside the API:

```bash
docker compose --profile slack up --build -d
```

Mention the app in a channel or send it a DM. Replies stream text and tool progress using Slack's
native agent APIs. Slack's agent features depend on your workspace's plan and admin settings.
Customize the app's name, icon, and description in Slack's app settings.

When writes are enabled, the agent presents the proposed action and approval controls. Set
`PAID_MEDIA_APPROVER_IDS=slack:<team_id>:<user_id>,...` to authorize reviewers. Approve verifies the
saved revision and payload; Reject stops the action. To change it, reject and ask the agent for a
revised proposal. Self-approval is disabled unless explicitly enabled. There are no tool-specific Slack cards.

## Deploy to your server

Clone the project on a host with Docker, configure `.env`, and run the same Compose command. Both
containers connect to the same Postgres service. Back up the Postgres and workspace volumes, and
protect the local `.env` and configuration files.

Socket Mode needs only outbound network access. To expose the API remotely, put an HTTPS reverse
proxy in front of port 8080 and keep bearer authentication enabled. Do not expose Postgres.

For Slack over HTTPS instead of Socket Mode:

1. Set `SLACK_TRANSPORT=http`, `SLACK_SIGNING_SECRET`, and `SLACK_BOT_TOKEN`.
2. Disable Socket Mode in Slack and point both **Event Subscriptions** and **Interactivity** at
   `https://your-host/slack/events`.
3. Start only the API and Postgres with `docker compose up --build -d`.

Bolt verifies Slack signatures and acknowledges events before running the agent. Accepted runs
continue in that server process; keep it running until they finish. The starter does not include
a durable background job queue.

## API and reports

`POST /threads/{thread_id}/messages` accepts `{"text":"..."}` and returns the completed response.
Proposal routes support read, approve, edit, and reject. This API does not implement the LangGraph
Agent Server protocol.

Download a generated report with `GET /threads/{thread_id}/artifacts/{name}` using the thread
owner's bearer token. Only files returned by `render_report` in that thread are accessible.
Slack replies can describe the report, but the adapter does not automatically upload files.

Use your existing scheduler for recurring self-hosted reports:

```bash
docker compose exec -T api paid-media-agent report --cadence weekly
```

MDA's `schedules/` declarations are managed by MDA; Compose does not run them automatically.

## Without Docker

```bash
uv sync --all-extras --dev
uv run paid-media-agent serve --port 8080
# In a second terminal, if Slack is configured:
uv run paid-media-agent slack
```

Set the same `DATABASE_URL` for both processes to share durable state. Without it, each process
uses its own temporary in-memory conversations. Install the native PDF libraries if you need PDF
reports; HTML reports remain available.
