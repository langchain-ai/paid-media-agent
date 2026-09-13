---
name: paid-media-org-onboarding
description: Help a user configure business context in the local checkout using the paid-media-agent CLI before deployment.
---

# Local business-context setup

Use this skill in a coding agent to collect and save the organization's context before its first
analysis. Work through the local CLI; the deployed agent has a separate tool-based interview.

1. Run `uv run paid-media-agent org show --json` and read existing answers first.
2. Read briefs, public links, or text files the user shares. Ask only for missing details, at most
   two questions per turn. Cover what they sell and to whom, conversion definitions, targets,
   budget and currency, markets and timezone, seasonality, campaign naming, and approvers.
3. Save answers with `uv run paid-media-agent org set field="answer"`. Quote shell arguments
   safely. Use `org add-link URL` and `org add-file PATH` to import sources. Never overwrite
   unrelated answers or invent a target. Empty fields can stay empty.
4. Confirm what was saved and offer a first analysis. Stop interviewing when the user asks.

The CLI writes `docs/org/profile.json`, renders the context pages, and keeps imported briefs in
`docs/org/sources/`. These files stay out of Git. Update them locally before deployment; hosted
changes do not sync back to the checkout.

Never ask for API keys or provider account IDs in chat. Those go through the setup console or
`config set`. Do not run the interactive `org interview` on the user's behalf; it is the manual
terminal path. The deployed interview lives in
[the runtime skill](../../../workspace/skills/paid-media-org-onboarding/SKILL.md).
