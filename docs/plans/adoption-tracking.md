# Plan: adoption and value tracking (pre-release decision)

Status: plan only. Nothing here is implemented, and the package sends no telemetry today
(see `docs/open-source-principles.md`, rule 20). Decide before the first tagged release.

## Goal

Answer, from Hex, four questions: how many people install this agent, how many reach a working
setup, how many run it on Managed Deep Agents or self-host with LangSmith tracing, and what value
it produces (questions answered, reports rendered, changes approved).

## Three layers, in increasing order of consent needed

1. **Signals we already own.** GitHub REST for stars, forks, clones, unique visitors, referrers, and
   release downloads (traffic data is kept 14 days, so snapshot daily). PyPI downloads through the
   public BigQuery dataset once the package is published; a git install leaves no trace.
2. **LangSmith fingerprint, no package telemetry.** Runs of this agent carry stable names: graph
   `paid-media-agent`; tools `compare_periods`, `summarize_window`, `render_report`,
   `propose_change`, `execute_change`; middleware `PaidMediaPortableToolSelector`. Count workspaces
   and deployments whose traces contain them; split MDA deployments (host control plane) from
   self-hosters who trace. Blind spot: self-hosters without tracing.
3. **Opt-out anonymous telemetry**, as PostHog, Next.js, and Supabase do it. A random install id
   under the user config directory; lifecycle events only (`installed`, `demo_run`,
   `setup_completed`, `platform_connected` with a count, `deployed` with runtime, `version`); no
   prompts, account ids, or keys; disclosed on first run and in the README; `PAID_MEDIA_TELEMETRY=0`
   disables it; endpoint configurable, posting to the LangChain Segment source. Requires changing
   principle 20 to "opt-out with disclosure".

## Hex model

- `github_daily`: snapshot of the traffic and release endpoints.
- `oss_events`: Segment events from layer 3, keyed by install id and version.
- `langsmith_agent_runs`: runs matching the fingerprint, with workspace, deployment, tool names.
- Join key: the install id, passed to a deployment as a secret by the CLI at deploy time.

Funnel: install, demo, setup complete, platform connected, deploy, first report, first approved
change. Value: weekly active installs, reports per workspace, approved changes per workspace, MDA
versus self-host share, time from install to first deploy.

## Effort

Layers 1 and 2 are warehouse jobs on the LangChain side. Layer 3 is about a day in this
repository plus a Segment write key, a README disclosure, and the principle change.
