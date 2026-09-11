---
name: paid-media-onboarding
description: Set up the fixture demo, choose a model, connect Pipeboard or direct platforms safely, map account aliases, or diagnose configuration without exposing secrets.
---

# Paid-media onboarding

Use this skill for setup, connection, model configuration, account mapping, and `doctor` failures.

1. Start with `uv run paid-media-agent demo --with-proposal`. It proves the install without any
   account or key.
2. Configure through `uv run paid-media-agent setup` (local page) or the same actions from the
   CLI: `config set PAID_MEDIA_MODEL=provider:model` plus the provider key under the name the
   provider expects. The setup console lists registered models per provider; Custom still takes a
   typed spec. The LangSmith Gateway is `langsmith:provider/model` with `LANGSMITH_API_KEY`.
   Registered Anthropic and OpenAI models use provider-native tool search; every other model,
   including gateway models, uses the portable selector.
3. Run `uv run paid-media-agent doctor` before connecting platforms. It names missing variables,
   packages, and native libraries without printing values.
4. Connect platforms: a scoped Pipeboard token for Google, Meta, and Reddit; direct credentials in
   `.env` for LinkedIn, X, and OpenAI Ads. Then `accounts discover` and `accounts add` to map
   aliases. Never paste provider account ids into chat; the model only ever sees aliases.
5. Check reads with `test pipeboard` and one CLI `ask` question. The setup console does not
   include Ask. Configure Slack only after the read path works; Socket Mode locally, the signed
   HTTP transport inside `serve` when hosted.
6. Leave writes disabled. Live write readiness is a separate operator workflow
   (`/docs/operations/live-write-runbook.md`).

When reporting an error, name the missing variable or capability without printing its value. Never
ask the user to paste a secret into chat.
