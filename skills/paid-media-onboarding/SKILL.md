---
name: paid-media-onboarding
description: Set up the fixture demo, choose a model, connect Pipeboard or direct platforms safely, map account aliases, or diagnose configuration without exposing secrets.
---

# Paid-media onboarding

Use this skill for setup, connection, model configuration, account mapping, and `doctor` failures.

1. Start with `uv run paid-media-agent demo --with-proposal`. It proves the install without any
   account or key.
2. Open `uv run paid-media-agent setup` for Welcome → Model → Accounts → Deployment. Configure
   through the console or CLI: `config set PAID_MEDIA_MODEL=provider:model` plus the key that the
   provider expects. The setup console loads current models from the provider's official API after
   a key is available. The same catalog is `uv run paid-media-agent models --provider langsmith --json`.
   Catalog reads do not save a draft key or send a prompt. If a catalog is unavailable, enter the
   provider's model ID manually. Custom still takes a typed spec.
   Saved nonblank keys override shell values; clearing a key removes its console export.
   Connection checks apply to the effective configuration and expire when its credentials change.
   The LangSmith Gateway is `langsmith:provider/model` with `LANGSMITH_API_KEY`.
   Registered Anthropic and OpenAI models use provider-native tool search; every other model,
   including gateway models, uses the portable selector.
3. Run `uv run paid-media-agent doctor` before connecting platforms. It names missing variables,
   packages, and native libraries without printing values.
4. Connect platforms: a scoped Pipeboard token for Google, Meta, TikTok, Pinterest, Snap, Reddit, LinkedIn,
   and Google Analytics; direct credentials in `.env` for X and OpenAI Ads. Then `accounts discover` and `accounts add` to map
   aliases. Never paste provider account ids into chat; the model only ever sees aliases.
5. Check reads with `test pipeboard`, discover and choose accounts, then deploy from the final
   console step. MDA is the recommended paid option: the Deploy agent action checks the project and
   starts deployment. Finish Slack authorization if requested, then Continue deployment. A local
   preflight does not prove cloud permissions. Self-hosting uses API/Postgres with optional Slack.
   MDA and Self-host are visible expandable paths. Studio is under Develop locally; CLI `ask`
   remains available. Agent settings sits below LangSmith setup in one column, with message triggers
   and report timing/timezone visible. Slack appearance expands for branding and preview.
   The final Deploy action sits below all settings and saves them before deployment.
   The sandbox is included by default: MDA bakes `sandbox/setup.sh` from the declared Python base
   during deploy/dev and reuses the snapshot. Do not ask users to publish one separately.
   `sandbox publish/use/test` remain optional standalone tooling. Sandbox PDF libraries do not
   change host report rendering; self-hosted Docker includes those native libraries separately.
   New users get account, plan, and API-key links without leaving setup. The same `PAID_MEDIA_SLACK_*`
   and report settings are exposed by `config show`/`config set`; see OPERATIONS.md. Use `config set`
   for timing so MDA's literal schedule declarations stay synchronized. Custom icons live at
   `channels/slack-icon.png` (still 512×512 PNG, at most 1 MB). Redeploy to apply changes.
   The Slack name does not rename the deployment or change self-hosted Slack app settings.
   Self-host setup groups storage/API access, optional Slack, and the final Docker command. Existing
   databases and direct API startup remain in expandable sections. Weekday, monthly-day, and time selectors
   keep native keyboard behavior; brief UI motion is skipped for keyboard and reduced-motion users.
   Time offers quarter-hour choices and preserves any existing minute-specific value.
   Timezone uses the same dropdown with browser-supported IANA zones, UTC, and the saved value
   so existing aliases are preserved. Self-hosted Slack fields explain where to find each token;
   app-level tokens need `connections:write` under Basic Information and Socket Mode enabled.
   Accounts shows one connection list. Pipeboard groups Google, Meta, TikTok, Pinterest, Snap, Reddit,
   LinkedIn, and Google Analytics above one token form and a link to pipeboard.co/connections.
   X and OpenAI Ads have separate rows that open their credential forms in Advanced.
   Users can connect any subset; a failed connector does not block available accounts or GA4 properties.
   Sample data is a secondary action below, with synthetic Google, Meta, and Reddit accounts only.
   Advanced groups configuration and hosting in expandable cards, with terminal
   commands below the controls. Approval and write-gate configuration is CLI-only; runtime checks remain.
   The console does not include chat.
   `PAID_MEDIA_DATA_MODE=sample` forces synthetic accounts even with live credentials saved.
6. Leave writes disabled. Live write readiness is a separate operator workflow
   (`/docs/operations/live-write-runbook.md`).

When reporting an error, name the missing variable or capability without printing its value. Never
ask the user to paste a secret into chat.
