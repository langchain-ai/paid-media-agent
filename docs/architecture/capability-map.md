# Capability map

| User capability | Agent entry | Trusted implementation | State | Main failure signal |
|---|---|---|---|---|
| Run fixture demo | `paid-media-agent demo` | `runtime/local.py` + scripted model + `tools/compute.py` | thread + `workspace/analysis` artifacts | fixture/schema mismatch |
| Discover tools | `discover_tools` | `tools/catalog.py` + `middleware/tool_selection.py` | catalog revision | stale or unknown tool |
| Read platform data | `<platform>__<tool>` | `tools/reads.py` dispatcher + guard | artifact metadata | auth, scope, schema, or partial source failure |
| Summarize performance | `summarize_window` | `tools/summary.py` | per-entity totals, pacing, and daily series artifact | unsupported metric, grain, or window |
| Compare performance | `compare_periods` | `tools/compute.py` | `PeriodComparison` artifact | incompatible window, grain, unit, or currency |
| Generate report | `render_report` | `reports/render.py` + bridge | artifact receipt | reconciliation or render failure |
| Propose change | `propose_change` | `tools/writes.py` `ProposalService` | persisted ChangeSet | invalid target or policy denial |
| Edit proposal | a new proposal in chat (Block Kit edit on a custom channel) | proposal revision service | new digest and revision | stale approval |
| Approve or reject | the Slack card (MDA) | approval service | signed claim or rejection | identity, expiry, replay, or signature failure |
| Execute change | `execute_change` after interrupt | `WriteExecutor` behind `WriteGate` | attempt record | kill switch, gate refusal, stale catalog or policy, provider error |
| Discover admitted mutations | `discover_write_operations` | validated `WritePolicyFile` | policy issues in `doctor` | row fails validation against the current catalog |
| Verify change | resumed graph | bounded readback adapter | WriteReceipt | mismatch or unknown outcome |
| Deliver artifact | `render_report` files | host artifact bridge | artifact receipt | unsafe path, type, size, or delivery error |
| Read business context | runtime skills | `workspace/skills/company-context/` | curated Markdown, excluded from Git | missing definitions or targets remain unknown |
| Run on MDA | `agent.py` | shared components + MDA config | managed thread and sandbox | deployment/config mismatch |
| Run self-hosted | `serve`, `slack`, `docker compose up` | shared components + Postgres (`runtime/self_hosted.py`) | self-hosted thread | auth, persistence, or adapter mismatch |
| Run locally | `paid-media-agent ask`, `report`, `mda dev` | the same components compiled by `runtime/local.py` | in-memory thread | model key or catalog mismatch |
| Onboard and operate | `setup` console or CLI groups | `admin/actions.py` (host-side, no model) | `.env`, `config/accounts.toml`, process logs | doctor failures, invalid key, gate refusal |

Update this table whenever a capability, entry point, state owner, or terminal condition changes.
