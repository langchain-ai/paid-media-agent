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
  the self-hosted adapter's task updates. A step never carries arguments.
- A footer line on Slack replies that did work: helpers running, minutes since the request, and an
  estimated cost for the lead and its helpers, from dated list prices in
  `src/paid_media_agent/middleware/prices.toml`. The model never sees it.

Live provider writes remain disabled by default and require the documented release gates.

### Changed

- Clarify the README's capabilities, setup, deployment, and company customization guidance.
- Use the LangChain company logo in the README, with light and dark variants.
- Require `managed-deepagents` 0.10.1 or later (and `deepagents` 0.7.30 or later). Document MDA's
  agent and personal memory layers and the day-to-day `mda` commands, including
  `mda channels setup`.
- `PAID_MEDIA_SLACK_TRIGGER_MODE` (`thread` by default: one mention, then the thread's replies;
  or `mention`, `all`) replaces `PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES`, which MDA 0.10
  deprecated. Set `PAID_MEDIA_SLACK_TRIGGER_MODE=all` if you had the old key set to `true`.
- `mda deploy` now creates serverless deployments by default. The operations guide explains why
  live-write deployments should pass `--deployment-type dedicated`.
