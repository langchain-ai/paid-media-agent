# Phase plan

| Phase | Inputs | Deliverables | Acceptance evidence | Explicit non-goals |
|---|---|---|---|---|
| 1. Fixture read path | spec, wiki, Deep Agents docs | package, shared assembly, fixtures, CLI demo, analysis skill | clean offline demo and deterministic tests | live accounts, Slack, writes |
| 2. Pipeboard reads | live catalog, MCP docs, model docs | host catalog, account aliases, two selector paths, doctor | read-only smoke and three-model matrix | provider mutation |
| 3. Reports | analysis payload, rendering sources | typed report, PDF, presentation objects | value reconciliation and artifact checks | custom frontend |
| 4. Governed fake writes | HITL docs, write contracts | proposals, claims, fake executor, receipts | real-graph happy and rejection tests | live write |
| 5. Surfaces and runtimes | MDA, Slack, persistence docs | MDA entry, native/rich Slack, self-host API, Postgres | parity and restart recovery | public deploy |
| 6. Live-write readiness | current reviewed catalog | narrow adapters, kill switch, operator runbook | all offline and read-only gates | actual canary without approval |
| 7. Release | legal and maintainer decisions | license, security, contribution, CI, snapshot, docs | clean-clone onboarding | publishing without approval |

Each phase updates code, tests, the owning architecture page, the relevant business page and skill,
indexes, and append-only logs as one coherent change.

