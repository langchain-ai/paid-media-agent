# Changelog

## Unreleased

### Added

- Paid-media analysis through a shared Deep Agents assembly, with a credential-free fixture demo.
- A local setup console and CLI for models, account connections, and deployment.
- Pipeboard tool discovery and read-only direct adapters behind a host-controlled account catalog.
- Deterministic period comparisons and HTML/PDF reports with source reconciliation.
- Typed proposals, verified human approvals, one mutation attempt, and bounded readback receipts.
- Managed Deep Agents deployment with Slack and schedule declarations, plus a self-hosted API,
  Slack adapter, and optional Postgres persistence.
- Runtime skills and editable business context shared across both deployment paths.
- Every run's trace names the template it came from: `ls_template: langchain-ai/paid-media-agent`
  and `ls_template_version` metadata on the root run, on MDA and the local and self-hosted paths.
  Nothing about the deployment or its people; `PAID_MEDIA_TEMPLATE_TELEMETRY=false` turns it off.

- Background helpers on Managed Deep Agents: `account-puller`, `report-builder`, and
  `general-purpose` are async subagents for long multi-account pulls and full reports. The lead
  hands work off with `start_async_task` and ends its turn; when a helper finishes it wakes the lead,
  and the answer posts to the same Slack thread. Every helper is read-only by its tool list and runs
  its own copy of the invocation guard, redaction, offload, and call limits.
- Check-ins: `schedule_check_in` and `cancel_check_in` let the agent come back to a conversation
  later, for example two days after an approved budget change, on MDA runtime schedules. A daily
  `schedules/housekeeping.py` run deletes expired check-ins in code, with no model call.
- Slack shows each step while a run works, in paid-media phrasing ("Reading Google Ads campaign
  performance", "Comparing the two periods"): MDA's channel `status` plan, and the same phrases in
  the self-hosted adapter's task updates. A step never carries text the model chose: no
  arguments, and no skill, wiki page, or tool name the repository does not ship.
- A footer line on Slack replies that did work: helpers running, minutes since the request, and an
  estimated cost for the lead and its helpers, from dated list prices in
  `src/paid_media_agent/middleware/prices.toml`. The model never sees it.

- Easier deploys from a fresh checkout:
  - `config set KEY` with no value asks in your terminal without echoing, and refuses outside a
    terminal, so keys never pass through a chat.
  - `mda check` exits non-zero while blocked and names the variable to set. It warns when the
    deployed agent would answer from demo data or mixed data, when `config/accounts.toml` is
    missing, about a LangSmith service key, and about local files a plain deploy would upload.
  - `paid-media-agent mda deploy --yes` deploys a copy without `workspace/analysis`, `in`, `logs`,
    `out`, `sessions`, and `sources`. A plain `mda deploy` uploads them, since MDA ignores
    `.gitignore`. The setup console deploys the same copy.
  - `doctor` checks the configured model's key, and the self-hosted Slack and database variables
    only for self-hosting.
  - `config set` accepts `LANGSMITH_WORKSPACE_ID` and checks `PAID_MEDIA_MODEL`'s shape.
  - The demo labels its receipt as simulated.
  - A step-by-step deploy guide, [docs/deploy-mda.md](docs/deploy-mda.md), which the onboarding
    skill follows.
- MDA-first README, like the design agent's: an `install.sh` one-liner, then three commands to
  enter keys, map accounts, and deploy; a "say this to your coding agent" table; and a questions
  section. `accounts discover --add` maps every newly found ad account to an alias in one step.
  AGENTS.md routes each request to its skill.

Live provider writes remain disabled by default and require the documented release gates.

### Changed

- Clarify the README's capabilities, setup, deployment, and company customization guidance.
- Use the LangChain company logo in the README, with light and dark variants.
- Require `managed-deepagents` 0.10.1 or later (and `deepagents` 0.7.30 or later). Document MDA's
  agent and personal memory layers and the day-to-day `mda` commands, including
  `mda channels setup`.
- Pipeboard loads through `langchain.mcp` (FastMCP, MCP 2.x) instead of `langchain-mcp-adapters`.
  `mda build` 0.10 adds `langchain[mcp]` and `fastmcp` to the deployed image, which need MCP 2, so
  the old `mcp<2` pin made every MDA 0.10 deploy fail to build. Tools are listed and called with no
  elicitation handler, so a server cannot pause a host-side call.
- Require Python 3.12 or later. `managed-deepagents` 0.10.0 and 0.10.1 fail to import on 3.11
  (pydantic rejects a `typing.TypedDict` there), and MDA builds the deployment on your local
  interpreter, so a 3.11 checkout could not deploy. CI now tests 3.12 and 3.13.
- The default model is `anthropic:claude-opus-5-5`, and the console's provider cards start on
  current models: Claude Opus 5.5 (also through the LangSmith Gateway), GPT-6 Astra, and Gemini 4
  Argon. The capability registry and price table add the Claude 5.5, Fable 5.1, GPT-6, and Gemini
  4 models, with OpenAI's GPT-6 family on native tool search.
- `PAID_MEDIA_MODEL_EFFORT` sets reasoning effort for Anthropic, OpenAI, and LangSmith Gateway
  models.
- The LangSmith Gateway's tool selector offers its selection with `tool_choice="auto"` instead of
  forcing it. Models that always think, such as Claude Opus 5.5, refused the forced call, so every
  Gateway run on them failed.
- `PAID_MEDIA_SLACK_TRIGGER_MODE` (`thread` by default: one mention, then the thread's replies;
  or `mention`, `all`) replaces `PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES`, which MDA 0.10
  deprecated. Set `PAID_MEDIA_SLACK_TRIGGER_MODE=all` if you had the old key set to `true`.
- `mda deploy` now creates serverless deployments by default. The operations guide explains why
  live-write deployments should pass `--deployment-type dedicated`.
