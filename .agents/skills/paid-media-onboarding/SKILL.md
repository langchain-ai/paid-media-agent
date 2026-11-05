---
name: paid-media-onboarding
description: Install and configure Paid Media Agent, connect ad platforms, choose MDA or self-hosting, and diagnose setup without exposing credentials.
---

# Set up Paid Media Agent

1. Read `README.md`, install with `uv sync`, then run
   `uv run paid-media-agent demo --with-proposal` to verify the fixture path without credentials.
2. Configure the model and its key through `uv run paid-media-agent setup` or
   `uv run paid-media-agent config set`. Use `provider:model`; LangSmith Gateway is optional.
   Never take a key in chat: ask the person to run `uv run paid-media-agent config set <KEY>` in
   their own terminal (it asks for the value without echoing it) or to use the setup console.
   Run `uv run paid-media-agent doctor` and resolve missing dependencies or configuration.
3. Connect any supported Pipeboard accounts; X and OpenAI Ads use direct credentials.
   Use `accounts discover` and `accounts add` to select aliases. Check connections before
   relying on live data. Keep secrets and provider account IDs out of chat.
4. Follow the `paid-media-org-onboarding` skill to write business context and custom runtime
   skills locally. The setup console configures connections and deployment, not business context.
   Offer company report styling through `paid-media-design`. Record lasting brand choices in
   `workspace/skills/report-design/DESIGN.md` and apply the matching renderer tokens. Use the
   shipped defaults when no company style is supplied.
5. Explain the deployment options in `OPERATIONS.md`. MDA manages the runtime, sandbox, and Slack;
   self-hosting uses Docker, Postgres, and an optional Slack app. For Slack on MDA, follow
   "Deploy to Slack" in `OPERATIONS.md` step by step:
   - Pipeboard: sign-up and token, then `test pipeboard`, `accounts discover`, `accounts add`.
   - Run `uv run paid-media-agent mda check` until it reports no blockers, and read its warnings
     to the person (demo data, missing `config/accounts.toml`, local files).
   - Ask before deploying; it is paid and outward-facing. Then run
     `uv run paid-media-agent mda deploy --yes`, never a plain `mda deploy`, which uploads local
     working files.
   - Tell the person what deploy may ask mid-run: a LangSmith sign-in, which Slack app to use, and
     a Slack authorization link that a workspace admin may need to approve.
6. When it is live, have the person message the app in Slack (under **Apps**) or `/invite` it to
   a channel and mention it, with a first question about last week's spend. If nothing comes back,
   read `uv run mda logs --no-follow`. Provide the deployment URL. A local preflight alone does
   not prove a deployed agent works. Keep provider writes disabled unless the operator completes
   `docs/operations/live-write-runbook.md`.

Use [customization](../../../docs/customization.md) for workspace context, runtime skills,
memory, and optional warehouse connections. Report missing configuration by name without its value.
