# Your organization's context

This folder is yours and stays out of version control. It holds a short profile the agent reads
before every analysis: what you sell, the conversion that counts, targets, budget, markets,
seasonality, campaign naming, approvers, plus any briefs or exports you share.

Fill it two ways, both producing the same files:

- the local coding agent: ask it to "learn about my business". It reads existing answers and
  briefs, asks only for missing details, and saves through the `org` CLI using
  `skills/paid-media-org-onboarding/SKILL.md`.
- manually, from the project folder: run `uv run paid-media-agent org interview`. Answer
  the eight terminal prompts; Enter keeps an existing answer or skips an empty field.
  Use `uv run paid-media-agent org set business="..."` for an individual update,
  `org add-link URL` for a public brief, or `org add-file PATH` for a local text file.

The setup console offers a copyable coding-agent handoff and manual commands under
**Advanced → Guides → Business context**. It does not collect business answers or make the
interview a deployment requirement. Secrets and account ids still go through the console.

Files: `profile.json` (source of truth), `goals.md` and `conventions.md` (rendered for the agent),
`sources.md` and `sources/` (links and files). Change profile answers through `org set`, which
regenerates the Markdown pages; deleting a rendered page does not remove the saved answer.
The agent reads all
of it through the `get_org_context` tool, so the same context is available locally and in the
deployment. `mda deploy` uploads this folder with the project; run the interview before you
deploy, because answers saved by the hosted agent live on that deployment until the next deploy.
MDA changes do not sync back to your checkout. For self-hosting, Docker Compose mounts
this folder into the API container so local and hosted tools read and write the same files.
