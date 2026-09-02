---
name: paid-media-onboarding
description: Set up the local fixture demo, choose a model, connect Pipeboard safely, map account aliases, or diagnose configuration without exposing secrets.
---

# Paid-media onboarding

Use this skill for setup, connection, model configuration, account mapping, and `doctor` failures.

1. Start with `uv run paid-media-agent demo`. It proves the install without external accounts.
2. Copy `.env.example` to `.env` and set only the chosen model provider key.
3. Configure `PAID_MEDIA_MODEL` as `provider:model`. Do not add a model gateway. Registered
   Anthropic and OpenAI models use provider-native tool search; every other model uses the portable
   selector. A custom `PAID_MEDIA_MODEL_BASE_URL` always uses the portable selector.
4. Run `uv run paid-media-agent doctor` before connecting Pipeboard. It names missing variables,
   packages, and native libraries without printing values.
5. Create a scoped Pipeboard token and connect platforms in Pipeboard.
6. Map human-readable account aliases in the accounts TOML (see `config/accounts.example.toml`).
   Never paste provider account ids into chat; the model only ever sees aliases.
7. Run a read-only connection check (`PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q`)
   and inspect the discovered catalog summary.
8. Configure Slack only after the agent read path works. Use Socket Mode locally.
9. Leave writes disabled. Live write readiness is a separate operator workflow.

When reporting an error, name the missing variable or capability without printing its value. Never ask
the user to paste a secret into chat.
