---
name: paid-media-onboarding
description: Install and configure Paid Media Agent, connect ad platforms, choose MDA or self-hosting, and diagnose setup without exposing credentials.
---

# Set up Paid Media Agent

1. Read `README.md`, install with `uv sync`, then run
   `uv run paid-media-agent demo --with-proposal` to verify the fixture path without credentials.
2. Configure the model and its key through `uv run paid-media-agent setup` or
   `uv run paid-media-agent config set`. Use `provider:model`; LangSmith Gateway is optional.
   Run `uv run paid-media-agent doctor` and resolve missing dependencies or configuration.
3. Connect any supported Pipeboard accounts; X and OpenAI Ads use direct credentials.
   Use `accounts discover` and `accounts add` to select aliases. Check connections before
   relying on live data. Keep secrets and provider account IDs out of chat.
4. Follow the `paid-media-org-onboarding` skill to write business context and custom runtime
   skills locally. The setup console configures connections and deployment, not business context.
5. Explain the deployment options in `OPERATIONS.md`. MDA manages the runtime, sandbox, and Slack;
   self-hosting uses Docker, Postgres, and an optional Slack app. Review the chosen settings,
   then deploy only when the user requests it. MDA includes the declared sandbox setup recipe.
   Inspect source files before deployment: MDA archives ordinary project files even if Git ignores
   them. Keep sensitive source briefs outside the deploy directory.
6. Verify the resulting deployment and provide its URL. A local preflight alone does not prove
   a deployed agent works. Keep provider writes disabled unless the operator completes
   `docs/operations/live-write-runbook.md`.

Use [customization](../../../docs/customization.md) for workspace context, runtime skills,
memory, and optional warehouse connections. Report missing configuration by name without its value.
