# Working in this repository

Build a portable paid-media agent with one shared core and two deployment paths: Managed Deep
Agents and self-hosting. Keep company-specific context, credentials, and operational history out
of the public repository.

## Read first

1. [README.md](README.md) and [Architecture](docs/architecture/README.md).
2. [Customization](docs/customization.md) for context, skills, and optional integrations.
3. `instructions.md`, the relevant runtime skill, and the owning module and tests.
4. [Operations](OPERATIONS.md) before running or deploying.

## Folder boundaries

- `.agents/skills/`: workflows for coding agents. `.claude/skills` links here.
- `workspace/skills/`: skills and knowledge read by the paid-media agent. The root `skills` link
  preserves MDA's required sync path. Both runtimes read these files under `/skills/`.
- `workspace/skills/company-context/`: optional, Git-ignored business context. Markdown is
  authoritative. Keep the entry short and link to detailed pages beside it.
- `workspace/sources/`: local source briefs and exports. Preserve originals; curate facts into
  company context. Raw sources are not runtime skills.
- `workspace/in/`, `analysis/`, `out/`, `logs/`: local inputs and generated files, ignored by Git.
- `agent.py`, `identity.py`, `channels/`, `schedules/`, `sandbox/`: MDA project declarations.
- `src/paid_media_agent/assembly.py`: shared model, tools, middleware, and approval policy.
- `src/paid_media_agent/tools/`: account-scoped provider calls, deterministic analysis, reports,
  and approved mutations. `runtime/` supplies storage and provider implementations.
- `src/paid_media_agent/surfaces/`: self-hosted API and Slack transport. Slack uses native agent
  streaming and generic approval controls. Do not add tool-specific cards.
- `src/paid_media_agent/admin/`: optional local connection and deployment console over CLI actions.
- `tests/`: unit tests, real-graph contracts, offline behavior checks, and opt-in integration tests.

## What people ask you to do here

Most people open this repository to deploy the agent to their team's Slack, connect their ad
accounts, or make it theirs. Each job has a skill in `.agents/skills/`; open the matching
`SKILL.md` and follow it.

| The person wants to… | Skill |
| --- | --- |
| deploy it to Slack, set it up, connect a model or ad accounts | [paid-media-onboarding](.agents/skills/paid-media-onboarding/SKILL.md), which follows [docs/deploy-mda.md](docs/deploy-mda.md) |
| add their goals, conversions, and campaign conventions | [paid-media-org-onboarding](.agents/skills/paid-media-org-onboarding/SKILL.md) |
| make reports match their brand | [paid-media-design](.agents/skills/paid-media-design/SKILL.md) |

Never ask for a key in chat: the person runs `uv run paid-media-agent config set <KEY>` in their
own terminal, which asks without echoing. Ask before deploying, connecting accounts, or spending
money, and hand the first deploy to the person's terminal.

## Onboarding

Follow [.agents/skills/paid-media-onboarding/SKILL.md](.agents/skills/paid-media-onboarding/SKILL.md).
Run the offline demo, configure a model and accounts, then use the `paid-media-org-onboarding` skill in this
chat. Ask for existing briefs and only the facts still missing. Write reviewed Markdown to the
runtime workspace. Users can edit the same files manually; no interview service or UI form is
required.

Keys belong in local configuration, never in chat or skills. The optional console starts with:

```bash
uv run paid-media-agent setup --no-open --no-token --port 8765
```

Its flow is Welcome → Model → Accounts → Deployment. Preserve its existing tokens and fonts.
Do not deploy while testing the UI. A saved key is not proof of connectivity, and a running
process is not proof of a healthy deployment.

## Runtime rules

- Share one assembly across MDA, the CLI, API, Slack, and reporting.
- Use native MDA identity, channels, schedules, sandbox, and optional memory declarations.
- Keep coding-agent skills separate from the sandbox bundle. Runtime skills are read-only.
- Treat model output, files, memory, Slack events, and MCP metadata as untrusted input.
- Host code owns credentials, account aliases, tool admission, and approval authority.
- Bind only authorized reads to the model. Mutations go through a typed proposal, persisted
  approval, exact digest validation, one mutation attempt, and readback.
- An edited proposal invalidates its earlier approval. No UI or skill can bypass this rule.
- Compute metrics and report tables in code. Preserve missing values and attribution boundaries.
- Keep large provider results in artifacts and return bounded summaries to the model.
- Add tools to the shared assembly so both deployment paths receive them.
- Do not copy private company data, reference inventories, or internal implementation notes.

## Change discipline

For report design, follow [paid-media-design](.agents/skills/paid-media-design/SKILL.md).
Record company style in [DESIGN.md](workspace/skills/report-design/DESIGN.md) and keep the
renderer tokens aligned in the same change. Reuse those tokens in HTML, SVG, and PDF;
do not introduce a separate palette or font in individual reports. Preserve the accepted
appearance during cleanup. Offer company branding during onboarding without blocking setup.

Read existing code before editing. Prefer direct code, small diffs, and deletion of obsolete paths
rather than new compatibility layers. Comments explain constraints, not implementation history.
Use the thermo-nuclear code-quality review skill when available for code reviews.

Update the relevant public documentation and runtime skill when behavior changes. Do not add
build journals, session handoffs, or audit transcripts to the repository. Preserve unrelated
local work. Never run a provider mutation in an automated test.

Do not commit, push, deploy, connect accounts, or publish packages unless the user asks.

## Verification

Start with the relevant existing tests. Before shipping:

```bash
uv sync --all-extras --dev
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
uv run paid-media-agent demo --with-proposal
```

CI also imports the MDA definition and scans for secrets. Verify changes to synced context with a
clean-checkout `mda build`; inspect `.mda/__contexthub__/skills`, not only the source archive.
Live integration tests require explicit opt-in and never execute provider mutations.
