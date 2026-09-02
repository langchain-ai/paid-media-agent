# Writes and approvals

The approval flow is an execution protocol, not a prompt convention.

## Contracts

- `ChangeSet` is the canonical proposal and presentation source.
- `ApprovalClaim` binds one proposal revision and digest to one requester, approver, account, tool,
  expiry, nonce, and signature.
- `WriteReceipt` reports a verified, rejected, failed, or unknown terminal state.

The review card and execution payload are derived from the same persisted `ChangeSet`. A surface
cannot submit replacement arguments during approval.

## Host checks

Before execution, trusted code verifies:

1. proposal exists and is awaiting approval;
2. revision and digest match;
3. approval is signed, fresh, unused, and for the current thread;
4. requester and approver identities satisfy policy;
5. account alias resolves to the configured provider account;
6. catalog revision and current tool schema are acceptable;
7. tool is admitted by write policy;
8. global incident kill switch permits execution.

The executor then records the attempt, calls the provider once, and performs bounded readback. A
timeout after the call creates an unknown state until read-only reconciliation proves the result.

## Rejection tests

Tests must prove denial for edited payloads, expired claims, replayed actions, foreign users, foreign
accounts, missing signatures, stale schemas, unknown tools, direct mutation calls, and runtime/profile
attempts to bypass the dispatcher.

## Implementation notes (2026-09-01)

- `propose_change` builds the `ChangeSet` from the current catalog entry and the reviewed
  `WritePolicy` (`WriteOperation` names the readback tool, target argument, editable fields, and
  risk). The before value comes from the authorized read provider, never from the model.
- `execute_change` is the only tool under `interrupt_on` (`approve`/`reject`). Resuming the graph
  grants nothing by itself: the executor loads the persisted proposal and the latest unused
  `ApprovalClaim` for that revision, verifies the HMAC signature, digest, scope, requester, and
  expiry, checks the current catalog entry and schema, then consumes the claim exactly once.
- Only `ProposalService.approve` creates claims. Surfaces call it with an opaque routing id or
  proposal id; Slack button values carry no payload.
- Readback runs through the authorized read path with bounded attempts and wall time. A timeout
  after submission is reconciled by readback: matched after-state is `verified`, matched before-state
  is `failed`, anything else is `unknown`. No mutation is ever retried.
- `WriteGate` admits fakes unconditionally and refuses live providers while
  `PAID_MEDIA_WRITES_ENABLED` is false or the Slice 6 canary is unreleased. No runtime profile
  constructs a live write provider today.
