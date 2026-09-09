---
name: paid-media-org-onboarding
description: Learn an organization's goals, conversions, targets, budget, markets, naming, and approvers through a short interview, accept links and files, and save them so every later analysis uses them.
---

# Organization onboarding

Use this skill when `get_org_context` returns mostly "Not provided", when the user asks
to set up, onboard, or "tell you about the business", or when an analysis needs a fact only the
organization knows (a target, the conversion that counts, a naming convention).

## How to run the interview

1. Call `get_org_context` first. Ask only about empty fields.
2. Ask at most two questions per turn, in plain language, each with one short example. The eight
   questions, in order, are the ones `update_org_profile` accepts: what you sell and to whom; the
   conversion that counts per platform; targets or "directional"; monthly budget and currency;
   markets and timezone; seasonality and planned spikes; campaign naming; who approves changes.
3. Offer to take links or files at any point: "If you have a brief, a planning doc, or a dashboard
   export, share the link and I will read it." For a public https link call `add_org_source`.
   Files are attached through the setup console or `paid-media-agent org add-file`; say so.
4. Save after every answer with `update_org_profile`, passing only the fields just answered.
   Never rewrite a field the user did not change.
5. Confirm in one sentence what was saved, then ask the next question or offer a first
   analysis that uses the new context ("Want the last complete week against your CPA target?").

## Rules

- Accept plain answers; do not demand precision. "About 60k a month" is an answer.
- Never ask for API keys, tokens, or provider account ids. Aliases and credentials are host-owned.
- Never invent a target or a benchmark to fill a gap. Empty stays empty and is reported as such.
- Company context is private. Do not quote it into reports or Slack channels beyond what the
  question needs.
- Stop when the user wants to stop; the profile can be completed later.
