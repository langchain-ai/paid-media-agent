# Surfaces and presentation

## Presentation objects

Domain services produce versioned presentation models such as `AnalysisSummary`, `ReportSummary`,
`ProposalView`, and `ReceiptView`. Every surface renders these objects. None parses raw model tool
arguments or provider responses.

## Slack

Managed Deep Agents' native channel (`channels/slack.py`) is the deployed surface: mentions, direct
messages, threads, and an approve/reject card on `execute_change`. MDA renders that card; its
content is not customizable today, so the agent writes the proposal summary in chat right before
it calls `execute_change`, and the card sits under it.

The self-hosted path runs the rich adapter: `surfaces/slack/blocks.py` renders Block Kit review
cards (proposal with Approve, Edit, Reject; receipts; reports; answers folded to mrkdwn) and
`surfaces/slack/service.py` is the transport-neutral event and action service (dedupe and replay
protection, caller-to-thread mapping, mention and DM policy, approver lookup, proposal actions).
`socket_mode.py` and `http.py` are the two transports; signed HTTP verifies the Slack signature
and a five-minute replay window before parsing. `surfaces/api/app.py` is the FastAPI boundary
(health, thread messages, proposal read, approve, edit, reject, artifacts) behind constant-time
bearer lookup, and `surfaces/ui/views.py` maps a run outcome to `OutcomeView`.

Every message has accessible top-level text. Model prose is escaped, length-bounded, and never used
as an action id or routing value.

## Schedules

`schedules/` start the same agent on a cron with a prompt that asks for the weekly or monthly
report. A change the agent might propose still waits for a human approval.

## Chat style

The agent writes for chat: no markdown, short lines, a colon-terminated label for a section. The
rule lives in `instructions.md` and `.agents/skills/paid-media-wiki/answer-style.md`; `to_mrkdwn` in the
Block Kit renderer folds any leftover markdown for Slack.

## Setup console

The console under `admin/` is a local operator surface for configuration, account discovery,
connection tests, and fixed process control. It is plain HTML/CSS/JavaScript and calls the same
host actions as the CLI. Welcome → Model → Accounts → Deployment is the complete setup flow.
MDA is the recommended paid deployment; self-hosting stays available. No chat client or separate
frontend server is required. Deployment shows one primary MDA card with the current model,
accounts, and LangSmith access; self-hosting and local tools sit under Other ways to run.
Welcome and model setup have no sample-analysis shortcut; sample account mode and the CLI
demo remain available.

The model picker and `models --provider` command share `admin/model_catalog.py`: fixed official
endpoints, provider-specific credentials, bounded pagination, and safe errors. Catalog reads use
the runtime's effective credentials or an unsaved draft key without persisting the draft.
Connection checks invalidate when those effective credentials change. Availability is independent of the runtime's
verified tool-selection registry. Custom IDs remain available when a provider has no list API.

The console binds to localhost with a per-run token, or same-origin enforcement for an IDE pane.
Deployment starts only after an explicit click and a successful project preflight. MDA's Slack
authorization continuation accepts only Enter at a recognized prompt. A local check does not
verify deployment permissions. The agent itself runs in Slack, Studio, CLI, or the existing API;
self-hosted API/Postgres provides durable state.

Process polling updates controls in place, preserving keyboard focus and expanded output.
Account selections belong to individual discovered rows; provider IDs can overlap across platforms.

## Implementation notes (2026-09-08)

- `surfaces/runner.py` is the application service a transport uses: send, resume, approve, reject,
  edit, and receipt lookup, with per-caller thread ownership.
- `tools/write_tools.py::execute_change` takes the proposal id and the revision the model
  presented; on resume it records the reviewer's decision as a revision-bound approval claim, with
  the identity taken from `caller_ref`, then `x-mda-user-id`, then the LangGraph auth user. Only
  identities in `PAID_MEDIA_APPROVER_IDS` are accepted, and a refusal names the identity it saw.
