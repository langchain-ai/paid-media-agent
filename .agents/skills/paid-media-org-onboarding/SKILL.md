---
name: paid-media-org-onboarding
description: Set up or update a company's paid-media context and runtime skills in the local workspace. Use before deployment or when business goals, measurement, or campaign conventions change.
---

# Business context

Read [the customization guide](../../../docs/customization.md) and any existing
`workspace/skills/company-context/` before editing.

1. Use briefs, plans, and files the user provides. Keep original sources under
   `workspace/sources/`; preserve their contents and record the source and date.
2. Ask only for missing facts needed for the first analysis, at most two questions per turn:
   what they sell and to whom, conversion definitions, CPA or ROAS targets, budget and currency,
   markets and timezone, attribution windows, campaign naming, and planned launches.
   Leave unknowns explicit. Never invent targets or overwrite unrelated context.
3. Create or update `workspace/skills/company-context/SKILL.md` directly. Keep the entry short;
   link to topic pages beside it for detail. Record source links and dates for material facts.
   These Markdown files are authoritative. There is no generated profile or runtime interview.
4. Put repeatable paid-media workflows in `workspace/skills/<skill-name>/SKILL.md`, with a
   specific name, a description stating when to use it, and only the steps the runtime needs.
   Keep coding-agent setup and repository maintenance in `.agents/skills/`.
   If the supplied briefs include brand guidance, follow `paid-media-design` to record the
   company's report style in `DESIGN.md` and apply its tokens to the renderer.
5. Review the resulting context with the user. Explain that runtime skills are deployed to
   the agent. Run the documented checks before deployment.

Manual editing follows the same folder contract.

Keep credentials, provider account IDs, and access policy out of context. Configure them through
`.env`, `config/accounts.toml`, and the host's permission settings. Optional warehouses and dbt
are described in the guide; do not claim a connection exists until a read-only check succeeds.

Before MDA deployment, review the project files that will upload. Git-ignored raw source files
can still enter the source archive; keep sensitive originals outside the deploy directory.
