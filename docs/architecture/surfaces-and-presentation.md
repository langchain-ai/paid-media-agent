# Conversation surfaces

The shared `AgentRunner` drives caller-owned graph threads. The API and self-hosted Slack use
the same proposal service, approval policy, and persisted state. MDA supplies its own Agent
Server and Slack channel around the shared agent definition.

## Slack

MDA owns the managed Slack connection and message rendering through `channels/slack.py`.
The agent summarizes a proposed action before `execute_change` interrupts for approval.

Self-hosting uses one async Bolt app for Socket Mode and signed HTTP. Bolt verifies requests
and acknowledges events before starting the run. `SlackDelivery` sends assistant Markdown and
generic tool progress through Slack's native streaming API. The session is `processing` while
the agent works, `suspended` when approval is required, and `active` after completion or failure.
Tool progress includes the name and status, never arguments or raw results. No tool-specific
cards or paid-media report layouts are embedded in the Slack adapter.

The only custom Block Kit is a generic Approve/Reject action row. Button values are opaque
routing IDs. The host reloads the proposal and verifies reviewer identity, revision, and payload
before executing. Edits invalidate previous approval. Receipts remain ordinary agent messages.

HTTP events are processed in the server process after acknowledgment. Keep that process running;
this starter does not include a durable background queue or cross-process cancellation service.

## Self-hosted API

`POST /threads/{thread_id}/messages` returns a completed response with text, proposal, receipt,
and available actions. It is a small application API, not an implementation of the LangGraph
Agent Server protocol. Bearer tokens map to caller identities; threads belong to their creator.

Proposal routes support read, approve, edit, and reject. Report downloads use
`GET /threads/{thread_id}/artifacts/{name}`. The caller must own the thread, and the file must
appear in a persisted `render_report` result from that thread. Paths, file types, and sizes are
validated before delivery. Reports are generated as HTML/PDF files; the Slack adapter does not
automatically upload them.

## Setup and schedules

The setup console configures model access, connected accounts, and deployment. It does not host
agent chat or collect business knowledge. Coding agents and humans edit business context and
runtime skills in `workspace/`; see [business context](../customization.md).

MDA reads the schedule definitions in `schedules/`. Self-hosted users can schedule the CLI report
command with their existing scheduler. Both paths use the same reporting tools and approval
boundary. See [self-hosting](../self-hosting.md).
