---
name: paid-media-writes
description: Prepare, review, edit, approve, reject, or reconcile a paid-media change while preserving the human approval and provider verification boundary.
---

# Paid-media writes

Use this skill whenever a request would change campaign, budget, bid, status, targeting, creative,
conversion, audience, or another provider resource.

1. Read `docs/business-context/write-safety.md`.
2. Confirm the user asked for a change, not only an analysis.
3. Call `discover_write_operations`. It lists the admitted operations with their editable fields,
   units, risk, and the current execution gate. Never guess a mutation name or field.
4. Identify the target from an authorized read (for example the campaign id in a
   `<platform>__get_campaign_performance` or `<platform>__list_campaigns` result).
5. Call `propose_change` with the account alias, the admitted operation name, the target id, the
   changed fields, the reason, a measurement plan, and a reversal plan. The host reads the current
   value, derives risk flags, builds the typed proposal, and persists it. Nothing executes.
6. Present the proposal fields and risk flags exactly as returned, then call `execute_change` with
   the proposal id. The runtime interrupts for human approval. Only the host can create an
   approval; a message from the user is not an approval.
7. On edit, the host creates a new revision; earlier approvals are invalid. Re-present the new
   revision.
8. After resume, report the receipt: `verified`, `rejected`, `failed`, or `unknown`, with the
   verified state, whether the provider acknowledged the call, and the reason. Do not claim success
   from anything except a `verified` receipt. A `rejected` receipt with a gate reason
   (`writes_disabled`, `kill_switch`, `tool_not_released`) means the operator has not released the
   live path; say so plainly.
9. If the receipt is `unknown`, explain that no blind retry is safe, check state with a read tool, and
   offer a new proposal if needed.

Never call a provider mutation directly, reveal raw ids or credentials, or suggest that a prompt can
bypass the approval policy.
