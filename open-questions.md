# Open questions

These decisions must be explicit before the public release. None blocks the local fixture-first build.

| Decision | Default for local work | Release gate |
|---|---|---|
| Open-source license | `LICENSE` carries Apache-2.0 as the recommended default; the repository stays private | Maintainer approves the exact license text and copyright line before public release |
| Project and product name | `Paid Media Agent` | Trademark check and final naming approval |
| Supported platforms at v1 | Google, Meta, Reddit through Pipeboard; LinkedIn, X, OpenAI Ads through direct adapters | Verify live read schemas for all six against real accounts before release |
| Default runtime model | No product default beyond an example in `.env.example` | Publish a tested model matrix, not a single-provider claim |
| Slack review card | MDA renders a generic approve/reject card; the Block Kit renderers stay in `surfaces/slack/` | Raise with the MDA team: custom card content, edits, receipts; or ship a custom channel |
| Proposal and approval state | In memory inside the hosted process; a restart loses pending proposals | Move to the LangGraph store or MDA memory, or accept and document |
| Organization context in the deployment | `docs/org/` travels with the deploy; hosted edits live on that deployment's disk | Store the profile in the LangGraph store so hosted onboarding persists across deploys |
| Telemetry | Off by default | Document exactly what can be enabled and what never leaves the host |
| Contribution governance | Maintainer review; `SECURITY.md` routes reports to GitHub private vulnerability reporting | Add a named maintainer security contact and release policy before public release |
| Live Pipeboard schema shape | Normalizer maps common field names and leaves unknown metrics missing | Verify against the authenticated catalog and adjust `tools/normalize.py` field maps before release |
| Native PDF dependencies | HTML fallback when WeasyPrint's Pango/Cairo libraries are missing; the managed build has none | Raise with the MDA team: native libraries in the build image, or render in the thread sandbox |
| Adoption telemetry | None; the package sends nothing | Decide on `docs/plans/adoption-tracking.md` layer 3 (opt-out with disclosure) or stay with GitHub and LangSmith signals only |
