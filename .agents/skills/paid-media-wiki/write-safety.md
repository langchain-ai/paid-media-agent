# Write safety

Paid-media writes can spend money, stop delivery, alter measurement, or change who sees an ad. The
agent therefore separates analysis, proposal, approval, execution, and verification.

## Default posture

- Read-only by default.
- Global write kill switch off by default.
- No direct mutation tools in model context.
- No permanent delivery-resource deletes in v1.
- Creation defaults to paused or draft.
- Activation is a separate approval.
- One proposal revision per approval.

## Review content

The reviewer sees platform, account alias, target, current value, proposed value, reason, risk,
measurement plan, and reversal plan. Money includes currency and period. Status changes explain
whether delivery starts or stops.

## High-risk actions

Treat budget increases, bid changes, targeting expansion, conversion configuration, creative
publishing, audience uploads, attribution changes, and activation as explicit risks. The first public
release should enable narrow, reversible operations before broad creation or measurement changes.

## Unknown outcomes

A network timeout after submission is not a failure that can be retried safely. Record the attempt,
perform bounded read-only reconciliation, and return unknown if the provider state cannot be proven.
The next action is investigation or a new proposal, not replaying the old approval.

