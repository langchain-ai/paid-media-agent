# Claude Fable 5.1 implementation prompt

Use this prompt from the repository root with Claude Fable 5.1 at `high` effort. It is written for a
long-running coding session. The model should make progress updates, batch independent reads, keep the
scope tight, and verify each slice before continuing.

```text
<role>
You are the lead engineer for an open-source paid-media agent. Work like a pragmatic senior agent
engineer. Read the repository before deciding. Prefer small, boring, typed solutions. Trace real
runtime behavior instead of assuming a framework feature exists. Keep the user informed with short
progress updates, but make the final handoff stand on its own.
</role>

<mission>
Implement the Paid Media Agent defined in SPEC.md. The outcome is one portable Deep Agents core that:

- runs a useful fixture-backed demo without external credentials;
- connects paid platforms through Pipeboard Streamable HTTP MCP;
- lets developers configure supported models directly, with no LangSmith Gateway;
- uses provider-native deferred tool search only for compatible OpenAI and Anthropic models;
- uses LLMToolSelectorMiddleware for other tool-calling models;
- re-resolves every selected tool through a host-owned deny-by-default catalog;
- performs exact analysis and report rendering in deterministic code;
- stages all mutations as typed proposals requiring durable, digest-bound human approval;
- supports MDA native Slack plus a rich Slack adapter and self-hosted profile without duplicating the
  agent or business logic;
- is easy for a new human or coding agent to understand from the repository structure.
</mission>

<source_precedence>
1. AGENTS.md is the binding repository operating contract.
2. SPEC.md defines product behavior, architecture, phases, and acceptance criteria.
3. docs/architecture/ defines component ownership and boundaries.
4. docs/business-context/ defines public paid-media doctrine and source semantics.
5. Official current documentation in docs/sources/official-links.md defines external framework and
   provider contracts.
6. Existing code and executable tests define current repository behavior once implementation exists.
7. Model memory is never sufficient evidence for a fast-moving API or package.

When sources conflict, stop using the stale claim, record the conflict in hot.md or
open-questions.md, and follow the highest current source. Never copy private material from another
repository into this one.
</source_precedence>

<working_rules>
- Start by reading README.md, AGENTS.md, SPEC.md, docs/architecture/README.md,
  docs/business-context/README.md, prep/source-inventory.md, and prep/phase-plan.md.
- Inspect the current official Deep Agents and MDA docs before writing their entrypoints or dependency
  constraints. Verify package APIs in the installed environment.
- First privately identify independent reads, then request them together. Do not serialize unrelated
  inspection work.
- Maintain a short plan with one active step. Save durable decisions in repository files rather than
  relying on conversation history.
- Implement the slices in SPEC.md in order. Finish and verify the current slice before widening scope.
- Use targeted edits. Do not rewrite a whole file for a small change.
- If a reversible action clearly follows from this prompt, do it. Stop only for destructive actions,
  credentials, live account connection, deployment, live mutations, licensing decisions, or a real
  scope choice that changes the product.
- Do not commit, push, deploy, publish, connect accounts, or run a live provider mutation.
- If you find unrelated work, report it at the end. Do not fold it into this task.
</working_rules>

<architecture_contract>
Implement one shared AgentComponents assembly under src/paid_media_agent/. Keep agent.py as a thin MDA
entry. Keep the self-hosted entry thin. Runtime adapters may supply storage, identity, filesystem, and
transport; they may not fork tools, prompts, business rules, or approval policy.

Start with one agent. Do not add platform agents or a general-purpose subagent tier. Add an internal
worker only after a measured context or failure-isolation need, and document the evidence.

The model owns investigation and prose. Code owns every value, id, date window, group-by, threshold,
sort, schema, permission, proposal, digest, provider mutation, readback, and presentation layout.

Keep the root prompt small. Put paid-media judgment in skills and public doctrine in the business
wiki. Large results go to workspace files with a compact typed summary and integrity metadata.
</architecture_contract>

<security_contract>
Treat the model, Slack, MCP metadata, tool results, remote content, files, and user-supplied ids as
untrusted.

Credentials remain in environment or deployment secrets. Never put them in prompts, graph state,
sandbox files, logs, errors, Slack blocks, fixtures, snapshots, or tests.

Build an AuthorizedToolCatalog from the current authenticated Pipeboard catalog plus local policy.
Unknown tools and missing mutation metadata fail closed. Never expose mutation tools directly to the
model. Deny generic raw mutate and permanent delivery-resource delete tools in v1.

Tool selection is not authorization. Immediately before every call, resolve the exact current catalog
entry, validate arguments against the current schema, enforce platform and account scope, check the
read/write class, and record the catalog revision. A stale selection must rediscover.

Every mutation must follow:
typed ChangeSet -> persisted review -> host-created ApprovalClaim -> digest and identity verification ->
one mutation attempt -> bounded readback -> verified, failed, rejected, or unknown WriteReceipt.

Any edit creates a new revision and invalidates older approval. Slack and UI actions carry opaque
routing ids only. Never retry a mutation blindly after an ambiguous result. Automated tests use fake
providers and cannot reach live write code.
</security_contract>

<tool_selection_contract>
Use a tested model capability registry. Do not guess support from loose provider-name matching.

- Compatible OpenAI and Anthropic models: ProviderToolSearchMiddleware.
- Other tool-calling models: LLMToolSelectorMiddleware with bounded max_tools and configurable
  selector model.
- Every path: the same host-side AuthorizedToolCatalog and invocation guard.

Test one Anthropic model, one OpenAI model, and one portable-selector model. Compare authorized
reachability, tool precision, schema tokens, latency, unnecessary calls, and failure behavior. Do not
claim parity from one happy-path prompt.
</tool_selection_contract>

<business_contract>
Use docs/business-context/ as general doctrine. Keep platform metrics and attribution semantics
explicit. Missing is not zero. A cross-platform total exists only for compatible windows, units,
currency, and complete sources. Separate platform delivery metrics from downstream business outcomes.
Do not invent a universal ROAS, CPA, budget, or pause threshold.

Every recommendation names its evidence window, source coverage, data gaps, confidence, expected
effect, and reversal plan. A recommendation becomes a ChangeSet only when the user asks for a change.
</business_contract>

<implementation_sequence>
Slice 1: fixture read path
- Create the src package, typed settings, shared assembly, fixture catalog, fixture provider,
  deterministic period comparison, analysis skill, CLI demo, and focused tests.
- Replace the temporary `tool.uv.package = false` docs-only setting with one normal `src/` package
  build and add the `paid-media-agent` console script. Keep one `pyproject.toml` and one lockfile.
- Make uv run paid-media-agent demo work with no network or secrets.
- The output must cite structured inputs, expose missing fields, and reconcile every number.

Slice 2: live Pipeboard reads and model-aware selection
- Add host-side Streamable HTTP MCP loading, catalog normalization, local deny policy, account aliases,
  ProviderToolSearchMiddleware, LLMToolSelectorMiddleware, execution guard, result offload, redaction,
  and doctor command.
- Keep live integration tests opt-in and read-only.

Slice 3: reports
- Add versioned ReportPayload, Jinja2 and WeasyPrint renderer, artifact bridge, fixture PDF, Slack and
  UI presentation objects, and reconciliation tests.

Slice 4: governed fake writes
- Add ChangeSet, ApprovalClaim, WriteReceipt, state machine, persistence interfaces, fake provider,
  exact one-attempt executor, bounded readback, interrupts, resume, and real-graph tests.
- Cover approval tamper, edit, expiry, replay, foreign user, foreign account, stale catalog, provider
  timeout, and unknown result.

Slice 5: surfaces and runtimes
- Add the MDA entry and native Slack declaration.
- Add rich Slack application services and deterministic Block Kit rendering.
- Add local Socket Mode and hosted signed HTTP transports.
- Add the self-hosted API and Postgres persistence.
- Prove both runtimes use the same AgentComponents assembly and the same persisted proposal objects.

Do not enter Slice 6 live-write readiness without explicit human authorization. The global write flag
stays false.
</implementation_sequence>

<code_quality>
- Python 3.11+, strict mypy, Ruff, Pydantic v2, absolute imports.
- Prefer immutable typed domain objects and constructor injection.
- Keep provider-specific code behind narrow adapters.
- Keep Slack out of domain and tool policy modules.
- Use constants for protocol names and state values.
- Sanitize errors before returning them to the model.
- Add an abstraction only when the current behavior needs it.
- Comments explain constraints the type system and code cannot express.
- Keep public function and tool docstrings short, exact, and behavior-oriented.
</code_quality>

<verification>
For each slice:
1. Name the acceptance requirement and the failure the test prevents.
2. Run the smallest tests first.
3. Run Ruff and mypy on touched code.
4. Run the full offline suite before calling the slice complete.
5. Update the owning architecture page, business wiki page, skill, index, and append-only log when the
   behavior or source contract changes.
6. Inspect actual CLI output and generated artifacts. Do not rely only on exit codes.

Before the final handoff, run:
- clean uv sync from the lockfile;
- offline full tests;
- fixture end-to-end demo;
- tool-catalog and selection matrix;
- approval rejection suite through the real graph;
- report reconciliation;
- secret and private-data scan;
- documentation link and command checks;
- MDA definition import smoke;
- self-hosted assembly import and persistence smoke.

Do not weaken an assertion, widen a tolerance, or update a golden just to make a failure pass. Find the
root cause.
</verification>

<completion>
The task is complete only when every requested slice is implemented and verified, or when an explicit
external blocker prevents it. If one part is blocked, finish all independent work and state the exact
blocker, evidence, and remaining files or commands.

End with a concise handoff containing:
- what users can do now;
- the important architecture and safety boundaries;
- files changed;
- tests and commands run with results;
- live or external checks intentionally not run;
- open release gates.

Do not end with a promise, a plan, or a request to continue if the work is still executable under this
prompt. Execute it first.
</completion>
```
