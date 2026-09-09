# Log

Append-only record of material changes to this repository's behavior. Newest first. The build-phase
journal (2026-08-31 to 2026-09-03) is preserved in
[docs/history/build-log-2026-09.md](docs/history/build-log-2026-09.md).

## 2026-09-08 (Managed Deep Agents only)

- Probed the hosted deployment's filesystem through the SDK: `/skills` present, the wiki and
  `docs/org` absent. Moved the wiki under `skills/paid-media-wiki/` and added `get_org_context`
  so the organization profile reaches the model through a tool in every runtime.
- Cut the self-hosted profile, its API, Postgres persistence, Slack transports, LangGraph Server
  factory, sandbox backend, and Docker files from `main` onto the `self-hosted` branch; wrote
  `docs/self-hosting.md`. `ask`, `report`, and the console now compile the deployment's profile.
- Approval on the managed card: `execute_change` takes the presented revision and records the
  clicking identity as the approval claim; a refusal names that identity so it can be added to
  `PAID_MEDIA_APPROVER_IDS`, which the Deploy step now asks for.

## 2026-09-08 (release readiness and console walkthrough)

- Walked the setup console in a browser as a first-time user and fixed what confused: `uv run`
  prefixes on every shown command, markdown rendering for answers, provider-card selection for
  gateway models, the direct-platform hint, consistent step titles, a snapshot preflight row, and
  next steps on Done.
- Found the synthetic data had aged past "last week"; fixtures now anchor to today with a pinnable
  setting so the demo and the eval keep working.
- Verified the managed deployment end to end with a deployment-capable key: sandbox recipe baked,
  deployed, SDK run answered, both schedules registered. Slack provisioning stops at an OAuth grant
  only the workspace owner can give.
- Wrote `docs/open-source-principles.md` and added the repository gems it names: code of conduct,
  issue and PR templates, pre-commit, release workflow, Dockerfile plus compose, Makefile.

## 2026-09-03 (gap closure and clarity pass)

- Closed the top parity gaps that can be verified without live credentials: ad-group and creative
  grain on the direct adapters and the fixture catalog, five public playbook wiki pages routed from
  the analysis skill, and a repeatable question eval under `tests/eval/`.
- Clarity pass from two read-only reviews: removed dead code and duplicated helpers, wired the
  signed Slack HTTP transport into `serve` and the Edit reply into the Slack service, dropped the
  unused catalog TTL and schedule run mode, made `OPERATIONS.md` the command reference, rewrote
  the README quick start around the credential-free demo, corrected `AGENTS.md`, and moved build
  scaffolding under `docs/history/`.
