# Live-write canary runbook

Live provider mutations are off by default and stay off until an operator completes every step
below. Automated tests cannot reach the live path: no test sets the gate values, and the fixture
runtime never constructs a live write adapter.

## Gates, in the order the executor checks them

| Gate | Setting or artifact | Effect when it fails |
|---|---|---|
| Kill switch | file at `PAID_MEDIA_KILL_SWITCH_PATH` (default `workspace/KILL_SWITCH`) | every execution, including fakes, is refused with `kill_switch` |
| Global flag | `PAID_MEDIA_WRITES_ENABLED=true` | live execution refused with `writes_disabled` |
| Reviewed catalog | `PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION=<revision>` equal to the current catalog revision | refused with `live_writes_not_released` or `stale_catalog` |
| Canary allowlist | `PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS=<platform>__<tool>,...` | refused with `tool_not_released` |
| Reviewed policy row | `admitted = true` row in the write-policy file that validates against the catalog | the operation cannot be proposed at all |
| Signed approval | host-created claim for the exact revision and digest | refused before any provider call |

Every refusal produces a `rejected` receipt with the reason and moves the proposal to `rejected`.
A new proposal is required afterwards; approvals are never reused.

## Preparing a canary

1. Run `uv run paid-media-agent doctor`. Confirm the model, accounts, Pipeboard token, signing key,
   and approver list are configured, and that `write_policy` shows no validation issues for the row
   you intend to release.
2. Run the read-only live check: `PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q`.
   Note the printed catalog revision.
3. Read the live schema of the target mutation. Add or update its row in the write-policy file with
   the exact `target_arg`, editable fields, readback tool, readback field mapping, and any
   `validate_only_arg` or `idempotency_arg` the schema exposes. Restart and re-run `doctor`.
4. Pick one reversible operation on one non-serving or low-spend object (a paused campaign's daily
   budget is the reference canary). Never start with activation, creation, deletion, audience,
   conversion, or permission changes.
5. Set `PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION` to the revision from step 2 and
   `PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS` to that single tool. Set `PAID_MEDIA_WRITES_ENABLED=true`.
   Restart the runtime.
6. Confirm `discover_write_operations` reports the gate as live with one canary tool.

## Running the canary

1. Ask the agent for the exact change in a thread. Review the proposal card: before value, after
   value, risk flags, reason, measurement plan, and reversal plan.
2. An authorized approver (not the requester unless self-approval is enabled) approves.
3. The executor validates with the provider when the schema offers validate-only, runs exactly one
   mutation, then reads the object back with bounded attempts.
4. Read the receipt. `verified` means readback matched the approved change. `failed` means the
   provider refused or the object still shows the before value. `unknown` means the mutation may
   have applied but readback could not prove it; reconcile with a read tool and open a new proposal
   if needed. Never replay an approval.
5. Reverse the change through a new proposal to prove the reversal plan.

## Incident response

- Create the kill-switch file immediately: `touch workspace/KILL_SWITCH` (or the configured path).
  Pending approvals then fail closed with `kill_switch`; no restart is needed.
- Unset `PAID_MEDIA_WRITES_ENABLED`, `PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION`, and
  `PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS` before the next deploy so the switch can be removed safely.
- Collect the proposal id, revision, receipt, and catalog revision from the thread and the receipt
  store. Provider responses are not stored in presentation objects; use the provider console to
  confirm the object state.
- Record the incident in `log.md` and, if the cause was a schema or policy mismatch, fix the policy
  row before releasing again.

## What the canary does not prove

- Other operations, platforms, or accounts. Each new tool needs its own policy row and canary.
- Idempotency under provider retries when the schema exposes no idempotency argument.
- Readback for fields the readback tool does not return; such fields cannot be verified and the
  receipt will be `unknown`.
