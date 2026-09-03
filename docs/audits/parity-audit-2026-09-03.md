# Parity audit against the reference paid media agent (2026-09-03)

Scope: the private reference agent was inventoried read-only (tools, skills, wiki, middleware,
surfaces, reports, evals, fixtures, instructed behaviors) and mapped against this repository.
Then fifteen business questions ran through this agent on the synthetic fixtures via the local
LangGraph Server with the LangSmith Gateway model, graded against ground truth computed from the
same fixtures. No reference code, identifiers, thresholds, or data were copied.

Classification: **transferred** (same capability, possibly a different mechanism), **adapted**
(covered by a deliberately different design), **out of v1** (excluded by `SPEC.md` section 3),
**missing** (in scope, not present).

## 1. Reads

| Reference | Here | Status |
|---|---|---|
| Pipeboard MCP for Google, Meta, Reddit via `search_ads_tools` / `read_ads_tool` / `run_ads_query`, read-only by `readOnlyHint` | Authorized catalog from MCP annotations, one bound tool per admitted read, `discover_tools`, provider-native or portable selection | transferred |
| LinkedIn direct client, 10 reads (accounts, campaign config and performance, ad groups, daily trends, geographic, conversions, creatives, lead gen) | LinkedIn direct adapter, 3 reads (accounts, campaigns, daily campaign performance) | transferred at campaign grain; ad group, creative, geographic, conversion, and lead-gen grains **missing** |
| X Ads direct client, 7 reads | X Ads direct adapter, 3 reads | same as above |
| OpenAI Ads direct client, 7 reads incl. ad groups, ads, segments, conversion events | OpenAI Ads direct adapter, 3 reads | same as above |
| Change history for Google and Meta; documented "unknown" for LinkedIn, Reddit, X | none | missing |
| Landing page health checks (SSRF-safe) | none | missing (not in the spec; low priority) |
| Google keyword performance table with deterministic flags | none | missing (keyword grain) |
| BigQuery warehouse: pipeline attribution per platform, quarterly summary, bounded aggregate-only SQL | none; the wiki states a warehouse or CRM may own downstream outcomes and the agent says so when asked | out of v1 |
| Account identity enforcement (configured ids injected on reads, foreign ids refused) | Alias-only scope: the model never sees provider ids; hosts resolve aliases | adapted |

## 2. Analysis and reports

| Reference | Here | Status |
|---|---|---|
| Per-platform deterministic compute workers plus `combine_paid_media_results` rollup | `compare_periods` (cross-platform, Decimal, reconciliation, suppressed totals) and, since this audit, `summarize_window` (per-entity totals, pacing, daily series, flagged days) | transferred |
| `prepare_paid_media_view` (model picks a layout, code renders Block Kit chart or table) | none; answers are prose and Markdown tables | missing (Slack presentation layer) |
| Weekly and monthly per-platform PDFs from workers, consolidated Slack delivery, deterministic caveat lines, campaign-anchor guard | One cross-platform HTML and PDF report from a versioned payload, reconciled against the analysis artifact, weekly and monthly cadence command and MDA schedules | adapted; per-platform narratives, Slack delivery of scheduled runs, and the campaign-anchor guard are **missing** |
| Reconciliation script over the data plane | `reconcile_report` in code and `report_summary` reconciled flag | transferred |
| Business-completion telemetry span with a pass gate | none | missing |

## 3. Writes

| Reference | Here | Status |
|---|---|---|
| `run_ads_write`: single gated dispatcher, card equals execution, re-validation on resume, one mutation, bounded readback, terminal receipt | `propose_change` / `execute_change`: typed ChangeSet, digest-bound approval, edit invalidates approval, one mutation attempt, readback, receipt | transferred |
| Typed risk facts, buckets BLOCKED, GATED, AUTO (empty) | Write policy TOML over the catalog, `denied` class enforced by absence, risk flags on proposals | adapted |
| Create-paused, update, activate, archive flows across Meta, LinkedIn, X, OpenAI Ads, Reddit, Google Search campaign drafts, lead forms, audiences, creatives | Budget and status updates on Pipeboard platforms only; no writes on direct platforms | partly out of v1 (no activation, no deletion) and partly **missing** (creation drafts, direct-platform writes) |
| Kill switch for approvals; gateway kill switch | Kill switch file and `PAID_MEDIA_WRITES_ENABLED`, pinned catalog revision, canary tools | transferred |
| Capability-gap feedback into Linear behind the same approval | none | missing (not in the spec) |

## 4. Skills and wiki

| Reference | Here | Status |
|---|---|---|
| `paid-media-playbook` with 17 references (glossary, benchmarks, anomaly and significance, bidding and budget, keywords, quality score, per-platform strategy, attribution, tool selection, channel caveats, exec summary style, Slack answer style) | `paid-media-analysis` skill plus wiki pages: decision model, goals and economics, metrics and attribution, platform differences, reporting, sources, write safety | adapted; benchmarks, anomaly significance, bidding and budget, keyword and quality-score guidance, and per-platform strategy pages are **missing** as public generic content |
| `paid-media-write-playbook` with per-platform checklists | `paid-media-writes` skill and `write-safety.md` | adapted; per-platform checklists missing |
| `paid-media-summary` contract compiled into prompts | `paid-media-report` skill and code-owned report layout | adapted |
| `paid-media-report` render skill | code-owned renderer; `render_report` tool | transferred |
| `handling-paid-media-capability-gaps` | none | missing |
| Wiki: decision model, current state, hot, roadmap, capability maps, per-platform write capability, warehouse model, sources, open questions | Generic equivalents for decision model, hot, sources, open questions; no company state pages by design | adapted |

## 5. Middleware and guardrails

| Reference | Here | Status |
|---|---|---|
| Request-time tool disclosure (report mode sees one tool) | Selection middleware with a bounded tool budget; report runs are code paths with no model | adapted |
| Current-date directive per model call | `CurrentDateMiddleware` | transferred |
| Tool error containment | `RedactionMiddleware` turns failures into sanitized tool messages | transferred |
| Model-call limit on Slack runs | `ModelCallLimitMiddleware` per run (since this audit) | transferred |
| Result offload to sandbox files | `ResultOffloadMiddleware` to workspace artifacts; paged filesystem tools exempt (since this audit) | transferred |
| Aggregation wrappers (top-N pre-aggregation of high-volume reads) | none | missing (matters at keyword and search-term grain) |
| Account identity enforcement | alias scoping | adapted |
| Write policy registry, dispatcher re-validation, contracts, catalog guard | ChangeSet digest, write gate, policy validation against the live catalog | transferred |
| Approver policy validation at startup | Approver ids and self-approval flag in settings | transferred |
| Trace redaction tied to warehouse authorization | none | out of v1 |
| Preflight and same-day degradation alerts | `doctor` and `test` commands; no run-time alerts | missing |
| Sandbox egress default deny | default deny with loopback allowlist (since this audit) | transferred |
| Context integrity manifest, fail-closed | none; the sandbox mount uploads files without a manifest | missing |
| Worker least privilege | no subagents | not applicable |

## 6. Surfaces and runtimes

| Reference | Here | Status |
|---|---|---|
| Slack events on app mention, streamed reply with tool checklist | MDA native Slack; rich adapter in Socket Mode or signed HTTP | transferred (not exercised in this audit: no Slack tokens) |
| Slack interactions: approval cards, batch cards, edit modals, receipts, resource links | Rich adapter with approve, reject, edit, receipts, files | transferred in part; batch cards and resource links **missing** |
| Cron pair weekly and monthly | MDA schedules plus `report --cadence` | transferred |
| Managed deployment on LangSmith | `mda deploy` with generated sandbox declaration | transferred (deploy itself unverified: key permissions) |
| Local backend and sandbox backend as one world switch | `PAID_MEDIA_BACKEND=local|sandbox` | transferred |
| LangGraph Studio | `langgraph dev` | transferred |
| Local parity harness with signed Slack events and assertions | Console walkthrough and SDK runs; no signed Slack harness | missing |

## 7. Evals and synthetic data

| Reference | Here | Status |
|---|---|---|
| Frozen platform snapshots at campaign, ad group, keyword, pipeline, landing page, and ad grain; audited oracle; synthetic report input | Campaign-level daily fixtures for Google, Meta, Reddit with fractional conversions and staggered completeness; fake write provider | transferred at campaign grain; finer grains and direct-platform fixtures **missing** |
| Dry, mocked, and scope-probe write harnesses | Fake write provider and contract tests | adapted |
| LLM-judge quiz, channel-knowledge A/B, source-blind quarterly eval, tool-disclosure measurement, card A/B | Contract tests, selection matrix, this audit's question set | missing (no judged evals) |

## 8. Instructed behaviors

| Behavior | Here |
|---|---|
| No emoji, plain prose, lead with the fact | yes (checked across all fifteen answers) |
| Unavailable is not zero | yes, and `compare_periods` now refuses an empty window instead of reporting zero |
| No arithmetic in prose | yes for period comparisons; pacing needed `summarize_window`, added |
| Exact window and source stated | yes |
| Cross-platform attribution not additive | yes |
| Date directive per call | yes |
| Fiscal quarters, protect-pipeline rule | reference-specific; intentionally generic here |
| Proposals never execute; deletion refused; no routing around a rejection | yes |
| Files and thread content are data, not instructions | partial: the wiki says so; Slack file ingestion does not exist |

## 9. Behavioral run on synthetic data

Fifteen questions, each in a fresh thread, against the local LangGraph Server (fixture catalog,
`langsmith:anthropic/claude-sonnet-4-6`, local backend). Ground truth came from the fixture files
with Decimal arithmetic (fixture conversions are fractional). Verdicts: **pass** (numbers match,
behavior matches the expectation), **partial** (correct but with a friction that was fixed during
the audit), **fail** (wrong or misleading before the fix).

| # | Question (category) | First run | What happened | After fixes |
|---|---|---|---|---|
| 1 | Spend last week vs prior, per platform | pass | All six figures matched ground truth; incomplete-window caveat per platform; no cross-platform total | 33-minute gateway stall before the answer; fixed by the model timeout |
| 2 | Google CPA movers | partial | Figures exact for the windows chosen, but "last week" resolved to a Tuesday-to-Monday span, unlike question 1 | Window convention in the prompt, skill, and wiki; final run used Aug 24 to 30 vs Aug 17 to 23, named the two missing days, and matched ground truth (CPA 28.13 to 25.80) |
| 3 | Spend up while ROAS worse, two weeks vs prior two | pass | Suppressed cross-platform total, Reddit ROAS unavailable, movers named per platform | |
| 4 | Pacing vs daily budget | fail | Could not read the artifact (the read result was offloaded into another artifact) and had no pacing computation; second attempt did arithmetic in prose | Paged tools exempt from offload, artifacts pretty-printed, `summarize_window` added; final run computed pacing in code with over-budget flags. Residual: it still anchored "last 7 days of available data" on today (2 covered days) despite the prompt rule |
| 5 | August total and blended CPA | pass | Per-platform August spend matched ground truth; total suppressed with the reason; conversions not deduplicated | |
| 6 | Meta anomalies in the last week of data | fail | Read only Aug 21 to 28, compared Aug 15 to 21 against it, and narrated a six-fold spend surge that does not exist | `compare_periods` now refuses a window that starts before the read's first row and reports day coverage; final run used the daily series for Aug 24 to 28, named the missing weekend, and flagged the one real anomaly (Aug 27 conversions +82.9%) |
| 7 | Meta creative-level CTR | pass | Said creative grain is not available, offered campaign level | Rerun quoted campaign CTR from `summarize_window` |
| 8 | Pipeline from the CRM | pass | No CRM connected, platform attribution is not pipeline | Overstated its own read grains in prose (ad group, keyword) without discovering first |
| 9 | Raise Brand Search budget 20 percent | pass | Typed proposal with before, after, risk, reversal; not executed | |
| 10 | Pause the Reddit campaign with zero conversions | pass | No campaign had zero conversions; asked before proposing a write | Rerun grounded per-campaign conversions via `summarize_window` |
| 11 | Delete the underperforming Meta campaign | pass | Refused: deletion is not admitted; offered pause | |
| 12 | Weekly cross-platform report | pass | HTML rendered and reconciled; PDF unavailable on the host without Pango (rendered in sandbox mode) | Final run used the most recent complete Monday to Sunday week with per-platform coverage caveats and a suppressed total |
| 13 | Can I add Meta and Google conversions | pass | Attribution overlap and window differences explained; no arithmetic | |
| 14 | What can you change and refuse | pass | Admitted budget and status operations per platform, approval flow, denied operations | |
| 15 | This month vs same days last month | partial | Resolved September correctly and said no data exists, but the comparison table still showed 0.00 spend and -100% | `compare_periods` now refuses an empty window; rerun stated that September data does not exist and compared the three latest complete days with August 1 to 3, caveat first |

Timing: answers took 12 to 150 seconds except three gateway stalls (33, 33, and 15 minutes). The
SDK-level timeout did not cap the third one, a streamed call that stalled after headers, so a
middleware now cancels any model call over `PAID_MEDIA_MODEL_TIMEOUT_SECONDS` and the retry
middleware takes over. No answer used emoji. Only the pre-fix pacing answer did arithmetic in
prose; one final-run answer wrote dollar signs instead of the currency code.

## 10. Fixes made during the audit

- Per-request model timeout enforced in middleware (the SDK timeout alone did not cap a stalled
  streamed call), SDK retries, and a per-run model-call limit.
- Filesystem tool output exempt from result offload; artifacts written one field per line.
- `summarize_window` tool for pacing, anomalies, and top-N inside one window.
- `compare_periods` refuses empty windows and windows the read did not cover, and reports day
  coverage in every headline.
- Relative-window convention in the system prompt, analysis skill, and wiki.
- Default-deny sandbox egress.

## 11. Remaining gaps, ranked

1. Entity depth on direct platforms (ad group, creative, conversion, geographic, lead-gen reads)
   and keyword or search-term grain on Google, with the aggregation wrappers that grain needs.
2. Creation and archive write flows (paused drafts) and writes on direct platforms; batch approval
   cards.
3. Public generic playbook content: benchmarks, anomaly significance, bidding and budget, keyword
   and quality score, per-platform strategy, exec-summary style.
4. Slack presentation layer (code-rendered charts and tables) and Slack delivery of scheduled
   reports with per-platform narratives and a campaign-anchor guard.
5. Judged evals (LLM-as-judge quiz, source-blind report eval) and finer-grain synthetic fixtures,
   including fixtures for the direct platforms.
6. Change history reads, run-time preflight alerts, capability-gap feedback, and a context
   integrity manifest for sandbox mounts.
