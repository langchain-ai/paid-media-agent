---
name: paid-media-wiki
description: The paid-media business wiki the other skills route to. General doctrine on goals, metrics and attribution, the decision model, platform differences, benchmarks, anomalies, bidding and budget, reporting, write safety, and answer style. Read the page a question calls for, never the whole wiki.
---

# Paid-media business context

This wiki gives the agent enough general business context to analyze paid media without pretending
every company has the same goals, attribution model, sales cycle, or risk tolerance. Edit it in
`.agents/skills/paid-media-wiki/` in the checkout. At runtime, pages live next to this file at
`/skills/paid-media-wiki/<page>.md`.

## Read order

1. [Goals and economics](goals-and-economics.md)
2. [Metrics and attribution](metrics-and-attribution.md)
3. [Decision model](decision-model.md)
4. [Platform differences](platform-differences.md)
5. [Reporting](reporting.md)
6. [Write safety](write-safety.md)
7. [Sources](sources.md)

Read when the question calls for it:

- [Benchmarks](benchmarks.md) when asked whether a figure is good.
- [Anomalies and significance](anomaly-and-significance.md) for spikes, drops, and flagged days.
- [Bidding and budget](bidding-and-budget.md) for pacing and budget or bid changes.
- [Platform playbooks](platform-playbooks.md) for platform-specific grains and caveats.
- [Answer style](answer-style.md) before writing the final answer.

Use [hot.md](hot.md) for current public capability notes and [open-questions.md](open-questions.md)
for unresolved doctrine. Append material changes to [log.md](log.md).

## The organization layer

Generic doctrine lives here. The organization's own goals, conversions, targets, budget,
naming, and approvers are written during onboarding and returned by the `get_org_context` tool;
they take precedence wherever the two differ.

## Boundaries

- This wiki contains general doctrine and public sources.
- User goals, targets, margins, account ids, currencies, timezones, attribution settings, and approval
  policy come from host-owned configuration or current user input.
- Platform data describes platform delivery and attributed outcomes. It does not by itself prove
  incrementality.
- A remembered capability, metric, or field is not runtime evidence. Discover the live schema.
- Missing data stays missing. It is never silently converted to zero.
