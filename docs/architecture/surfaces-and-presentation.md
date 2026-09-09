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

`surfaces/slack/blocks.py` and `surfaces/slack/service.py` hold the Block Kit review cards
(proposal with edit, receipts, reports, answers folded to mrkdwn) and the transport-neutral event
and action service: dedupe and replay protection, caller-to-thread mapping, mention and DM policy,
approver lookup, proposal actions. They are tested against the real graph and kept for a custom
Slack channel; a transport supplies only event delivery and message posting.

Every message has accessible top-level text. Model prose is escaped, length-bounded, and never used
as an action id or routing value.

## Schedules

`schedules/` start the same agent on a cron with a prompt that asks for the weekly or monthly
report. A change the agent might propose still waits for a human approval.

## Chat style

The agent writes for chat: no markdown, short lines, a colon-terminated label for a section. The
rule lives in `instructions.md` and `skills/paid-media-wiki/answer-style.md`; `to_mrkdwn` in the
Block Kit renderer folds any leftover markdown for Slack.

## Setup console

The console under `admin/` is an operator surface, not an agent surface. It calls host actions
(doctor, config, discovery, tests, process control) that the CLI exposes with `--json`. It binds to
localhost, requires the per-run token, writes only local files, and starts only `mda dev` and
`mda deploy`. Deployment secrets stay in the deployment platform.

## Implementation notes (2026-09-08)

- `surfaces/runner.py` is the application service a transport uses: send, resume, approve, reject,
  edit, and receipt lookup, with per-caller thread ownership.
- `tools/write_tools.py::execute_change` takes the proposal id and the revision the model
  presented; on resume it records the reviewer's decision as a revision-bound approval claim, with
  the identity taken from `caller_ref`, then `x-mda-user-id`, then the LangGraph auth user. Only
  identities in `PAID_MEDIA_APPROVER_IDS` are accepted, and a refusal names the identity it saw.
