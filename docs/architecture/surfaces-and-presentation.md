# Surfaces and presentation

## Presentation objects

Domain services produce versioned presentation models such as `AnalysisSummary`, `ReportSummary`,
`ProposalView`, and `ReceiptView`. Slack and the Agent UI render these objects. They do not parse raw
model tool arguments or provider responses.

## Slack

MDA native Slack supplies the shortest managed path. The rich adapter supplies Block Kit, progress,
files, edits, and detailed receipts. Local and private self-hosted deployments use Socket Mode when a
public endpoint is undesirable. Hosted deployments may use signed HTTP events.

Both transports share:

- event dedupe and replay protection;
- caller-to-thread mapping;
- mention and DM policy;
- authorization and approver lookup;
- proposal action service;
- Block Kit renderers;
- artifact delivery policy.

Every message has accessible top-level text. Model prose is escaped, length-bounded, and never used as
an action id or routing value.

## Agent UI

The UI displays graph state and presentation objects. It may approve, edit, reject, or cancel through
the same application service as Slack. UI-only powers are prohibited.

## Schedules

Schedules start the same graph with an explicit run mode and scoped tool surface. A reporting schedule
receives read and render capability only. It cannot inherit conversational write tools as a fallback.

## Implementation notes (2026-09-01)

- `surfaces/runner.py` is the one application service: send, resume, approve, reject, edit, and
  receipt lookup, with per-caller thread ownership.
- Slack: `blocks.py` renders `ProposalView`, `ReceiptView`, `ReportSummary`, and progress with
  escaped, bounded text and opaque action values; `service.py` handles events and actions with
  dedupe and mention/DM policy; `socket_mode.py` and `http.py` are the two transports. Signed HTTP
  verifies the Slack signature and a five-minute replay window before parsing.
- API: `surfaces/api/app.py` exposes health, thread messages, proposal read/approve/reject/edit, and
  artifact download behind constant-time bearer token lookup.
- UI: `surfaces/ui/views.py` maps a run outcome to `OutcomeView` with the same presentation objects.
