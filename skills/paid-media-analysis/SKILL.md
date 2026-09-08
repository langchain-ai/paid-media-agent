---
name: paid-media-analysis
description: Analyze paid-media performance, compare periods or entities, diagnose issues, and make evidence-backed recommendations across connected ad platforms.
---

# Paid-media analysis

Use this skill for performance questions, audits, comparisons, diagnosis, budget reasoning, and
recommendations.

1. Read `/docs/org/goals.md` and `/docs/org/conventions.md` if they exist; they carry this
   organization's targets, conversions, and naming and override generic doctrine. Then read
   `/docs/business-context/decision-model.md` and the page the question calls for:
   `benchmarks.md` for "is this good", `anomaly-and-significance.md` for spikes and drops,
   `bidding-and-budget.md` for pacing or budget changes, `platform-playbooks.md` for a platform's
   grains and caveats, and `answer-style.md` before the final answer.
2. Establish goal, account scope, entity grain, date window, comparison, timezone, and currency.
   Comparison windows must have the same day count; `compare_periods` rejects unequal windows.
   Resolve relative windows one way and say which: "last week" is the most recent complete
   Monday to Sunday week; "last N days" ends on the latest date the platform reports as complete
   (`data_complete_through`), not today; "this month" is the calendar month to date. When a
   platform's data ends inside the requested window, keep the requested window in the answer and
   name the missing days rather than silently shrinking it.
3. Call `list_accounts` for aliases, then `discover_tools` with keywords. Never invent a tool name.
   Platform tools are named `<platform>__<tool>` and take `account_alias`, never a provider id.
4. Pull the smallest complete data: one `<platform>__get_campaign_performance` read per account for
   the union of both windows. Go one grain lower only when the question needs it:
   `get_ad_group_performance` (ad sets, line items) or `get_creative_performance` where the
   platform exposes it; rows carry the parent campaign id. Run independent platform reads in parallel. Each read returns a
   compact `read_result` with an `artifact_id`, row count, actual window, missing fields, and flags.
5. Validate source coverage with `references/validation-checklist.md`.
6. For pacing, anomalies, top spenders, or per-entity efficiency inside one window, call
   `summarize_window` with the performance artifacts (and the `list_campaigns` artifacts for daily
   budgets); it returns per-entity totals, pacing, and a daily series with flagged days. For
   period-over-period change, call `compare_periods` with the artifact ids and both windows. List any failed read in
   `unavailable_sources` so it stays visible and suppresses the cross-platform total.
7. Read the `analysis_summary`. Quote its values verbatim; never recompute from previews or rows.
   `unavailable` means missing, not zero.
8. Explain observation, business meaning, likely drivers, confidence, and next action separately.
9. Include a measurement and reversal plan for any recommendation.
10. Create a proposal only when the user asks to change provider state (see `paid-media-writes`).

Do not use universal performance thresholds. Use configured goals or label the analysis as directional.
