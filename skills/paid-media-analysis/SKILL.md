---
name: paid-media-analysis
description: Analyze paid-media performance, compare periods or entities, diagnose issues, and make evidence-backed recommendations across connected ad platforms.
---

# Paid-media analysis

Use this skill for performance questions, audits, comparisons, diagnosis, budget reasoning, and
recommendations.

1. Read `docs/business-context/decision-model.md`.
2. Establish goal, account scope, entity grain, date window, comparison, timezone, and currency.
   Comparison windows must have the same day count; `compare_periods` rejects unequal windows.
3. Call `list_accounts` for aliases, then `discover_tools` with keywords. Never invent a tool name.
   Platform tools are named `<platform>__<tool>` and take `account_alias`, never a provider id.
4. Pull the smallest complete data: one `<platform>__get_campaign_performance` read per account for
   the union of both windows. Run independent platform reads in parallel. Each read returns a
   compact `read_result` with an `artifact_id`, row count, actual window, missing fields, and flags.
5. Validate source coverage with `references/validation-checklist.md`.
6. Call `compare_periods` with the artifact ids and both windows. List any failed read in
   `unavailable_sources` so it stays visible and suppresses the cross-platform total.
7. Read the `analysis_summary`. Quote its values verbatim; never recompute from previews or rows.
   `unavailable` means missing, not zero.
8. Explain observation, business meaning, likely drivers, confidence, and next action separately.
9. Include a measurement and reversal plan for any recommendation.
10. Create a proposal only when the user asks to change provider state (see `paid-media-writes`).

Do not use universal performance thresholds. Use configured goals or label the analysis as directional.
