# Your organization's context

This folder is yours and stays out of version control. It holds a short profile the agent reads
before every analysis: what you sell, the conversion that counts, targets, budget, markets,
seasonality, campaign naming, approvers, plus any briefs or exports you share.

Fill it three ways, all producing the same files:

- the setup console, step "Your business" (`uv run paid-media-agent setup`)
- the CLI: `uv run paid-media-agent org interview` or `org set business="..."`, `org add-link`,
  `org add-file`
- the agent itself: ask it to "learn about my business" and it runs the interview and saves

Files: `profile.json` (source of truth), `goals.md` and `conventions.md` (rendered for the agent),
`sources.md` and `sources/` (links and files). Delete a file to forget it. The agent reads all
of it through the `get_org_context` tool, so the same context is available locally and in the
deployment. `mda deploy` uploads this folder with the project; run the interview before you
deploy, because answers saved by the hosted agent live on that deployment until the next deploy.
