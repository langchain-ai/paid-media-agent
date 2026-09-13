# Decision model

Use this workflow for analysis, recommendations, and change proposals.

## 1. Frame the decision

Identify the business goal, account scope, entities, date window, comparison, currency, and action the
user is considering. If a missing choice materially changes the answer, ask. Otherwise make the
smallest explicit assumption.

## 2. Discover capability

Search the current authorized catalog and inspect the selected schema. Confirm the account is connected
and the required grain, fields, and window exist. A tool name in documentation is not proof that the
current connection exposes it.

## 3. Gather evidence

Use the smallest complete pull. Prefer independent parallel reads for independent platforms. Preserve
raw results in workspace artifacts and return compact summaries.

## 4. Validate data

Check source, account, grain, window, timezone, currency, row count, nulls, duplicates, attribution,
and freshness. Mark partial sources and conflicting totals before interpretation.

## 5. Compute

Run deterministic analysis. The model does not perform arithmetic over raw rows. Reconcile entity and
account totals and retain the computation version.

## 6. Interpret

Separate observation, explanation, and hypothesis. Consider business outcome quality, channel role,
measurement coverage, seasonality, creative fatigue, audience saturation, learning state, and lag.

## 7. Recommend

A recommendation contains:

- exact target and scope;
- evidence and window;
- expected effect and uncertainty;
- data gaps and failure modes;
- proposed magnitude and duration when supplied by policy or the user;
- measurement plan;
- reversal rule.

## 8. Propose, do not mutate

Only create a `ChangeSet` when the user asks for a change. The proposal shows before and after values
from trusted data. Approval and execution are separate host-controlled states.

## 9. Verify

After an approved mutation, perform bounded provider readback. Report verified state, not provider
acknowledgment alone. If proof is unavailable, report unknown and reconcile with reads.

