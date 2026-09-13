# Agent workspace

Use this folder for runtime skills and local working files.

| Path | Purpose |
| --- | --- |
| `skills/` | Runtime skills and the general paid-media wiki |
| `skills/company-context/` | Your private business context, written by your coding agent or edited by hand |
| `sources/` | Original briefs and exports used to prepare context |
| `in/`, `analysis/`, `out/` | Runtime input, calculations, and report artifacts |

The root `skills` link points here so MDA and self-hosting load the same runtime skills.
Local coding-agent workflows live in `.agents/skills/` at the repository root.

Start with [customization](../docs/customization.md). Business context and source files are
Git-ignored. MDA can still include ignored files in its source archive, so keep sensitive original
briefs outside the deployment directory. Runtime skills are read-only to the agent; update them
locally and deploy the changes.
