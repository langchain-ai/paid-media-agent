# Paid Media Agent: product and engineering specification

## 1. Outcome

Build a useful open-source paid-media operator, not a framework demo. A developer can run it with
fixtures, connect real ad accounts through Pipeboard, choose a supported model directly, use the same
agent from Slack or an Agent UI, and approve exact provider changes before execution.

The product succeeds when it can answer a business question, show the evidence and data gaps, produce
a reconciled recommendation, stage a typed change, survive an interrupt or process restart, execute
the approved change at most once, verify the provider state with bounded readback, and return a receipt.

## 2. Users and core journeys

### Developer

- Clone the repository and run `uv sync --all-extras --dev`.
- Run `uv run paid-media-agent demo` with no external credentials.
- Set `PAID_MEDIA_MODEL` to a LangChain `provider:model` value or configure a compatible base URL.
- Add a scoped Pipeboard token and map local account aliases to connected provider accounts.
- Run `uv run paid-media-agent ask` locally, `mda dev` with Studio, and `mda deploy .` to Slack.
- Use `uv run paid-media-agent doctor` to diagnose configuration without leaking secrets.

### Paid-media operator

- Ask which campaigns, ad groups, ads, audiences, keywords, or creatives need attention.
- Compare a period with a complete and clearly labeled comparison period.
- See spend, delivery, conversion, efficiency, and downstream business evidence without false
  cross-platform precision.
- Generate an account or portfolio report with traceable numbers and visible missing data.
- Ask for a change, inspect its exact account, target, before value, after value, reason, and risk,
  then approve, edit, or reject it.
- Receive a verified receipt, or an explicit unknown state when the provider outcome cannot be proven.

### Maintainer

- Add a Pipeboard platform without adding a Slack branch or a new agent.
- Add model support by declaring verified capabilities, not by scattering provider conditionals.
- Update business judgment in one skill and one owning wiki page.
- Reproduce every release claim with a test, fixture, live read-only probe, or official source.

## 3. Scope

### Included

- One shared Deep Agents assembly.
- Fixture-backed local demo.
- Direct model configuration with OpenAI, Anthropic, Google, and compatible LangChain providers.
- Pipeboard Streamable HTTP MCP catalog, authentication, reads, and governed writes.
- Provider-native deferred tool search for compatible OpenAI and Anthropic models.
- `LLMToolSelectorMiddleware` for other tool-calling models.
- Host-side tool authorization and execution.
- Generic public paid-media business wiki and progressive skills.
- Deterministic cross-platform analysis and report rendering.
- Typed proposals, durable approval state, provider execution, readback, and receipts.
- MDA native Slack and a rich Slack adapter (Socket Mode and signed HTTP).
- Two deployment paths on one assembly: Managed Deep Agents (recommended, one command) and
  self-hosted (API, Postgres, Docker compose).
- Source-blind tests, deterministic oracles, security rejection tests, and context-cost checks.

### Not included in v1

- A second provider OAuth implementation when Pipeboard already owns the connection.
- LangSmith Gateway or any required model proxy.
- Autonomous changes, standing optimization loops, or approval reuse.
- Raw provider mutate-anything endpoints.
- Permanent deletion of delivery resources.
- Automatic activation of newly created campaigns or ads.
- A data warehouse, CRM, or attribution ETL product.
- Private company playbooks, account ids, thresholds, production history, or copied internal data.
- A swarm or per-platform agents without eval evidence that one agent is insufficient.
- A custom frontend before the standard Agent UI and Slack surfaces prove the domain contracts.

## 4. Architecture

### 4.1 One core, thin adapters

The shared core is a pure assembly layer. It creates the model, authorized tools, middleware,
instructions, skills, interrupt policy, and typed response contracts. Runtime adapters supply
persistence, filesystem backend, caller identity, and transport.

```text
agent.py (MDA)              runtime/local.py (CLI, demo, tests)
       \                         /
        build_agent_components(settings, runtime)
                         |
          model + tools + middleware + skills
                         |
                 Deep Agents graph
                         |
      Pipeboard / deterministic compute / write executor
```

`agent.py` must remain a small MDA entry that exports one named `agent`. The local entry compiles
the same components with `create_deep_agent` for the CLI and the tests. Shared behavior lives
under `src/paid_media_agent/`; surface-specific code does not enter the domain or policy modules.

The assembly API should look like this:

```python
@dataclass(frozen=True)
class AgentComponents:
    model: BaseChatModel
    tools: tuple[BaseTool, ...]
    middleware: tuple[AgentMiddleware, ...]
    interrupt_on: Mapping[str, InterruptOnConfig]
    response_format: type[BaseModel] | None


def build_agent_components(
    *, settings: Settings, runtime: RuntimeProfile, catalog: AuthorizedToolCatalog
) -> AgentComponents: ...
```

Do not hide network access, state mutation, or policy decisions in the assembly function. It composes
auditable components.

### 4.2 Control plane and data plane

The model is the control plane. It decides which question to investigate, which verified source is
relevant, how to interpret a result, and how to explain it.

Deterministic code is the data plane. It owns:

- date windows and timezone normalization;
- currency and unit handling;
- arithmetic, grouping, sorting, and thresholds;
- metric definitions and denominator checks;
- account and resource identity;
- data-quality flags and reconciliation;
- proposal schemas and payload digests;
- permissions, approval validity, and mutation count;
- report tables, formatting, and layout.

Raw rows go to `workspace/analysis/` as typed JSON or Parquet. Tools return a compact summary plus the
file path, row count, schema version, source window, and integrity hash. The model never recomputes a
number that code can assert.

### 4.3 Context architecture

Keep the always-loaded prompt small and stable. It contains role, source precedence, safety boundaries,
completion rules, and links to skills. Business doctrine lives in `.agents/skills/paid-media-wiki/`.
Reusable task workflows live in `.agents/skills/<name>/SKILL.md` with references, scripts, and
templates loaded on demand. The root `skills/` link preserves the runtime's `/skills/` paths.

Large tool results are offloaded before they crowd the conversation. Summarization must preserve user
intent, source windows, selected accounts, proposal ids, approval state, unresolved data gaps, and
artifact paths. Never compact by rewriting earlier provider thinking blocks in a way that breaks the
selected model's conversation contract.

## 5. Model configuration

### 5.1 Direct providers

`PAID_MEDIA_MODEL` accepts `provider:model`. `PAID_MEDIA_MODEL_BASE_URL` is optional for compatible
APIs. Provider packages are optional extras. Configuration is resolved once into a typed `ModelConfig`:

```python
class ModelConfig(BaseModel):
    provider: str
    model: str
    base_url: AnyHttpUrl | None = None
    tool_selector_model: str | None = None
```

No code path requires a LangSmith model gateway. LangSmith credentials are used only when the chosen
MDA or LangSmith deployment needs them.

### 5.2 Capability registry

Do not infer behavior from a provider-name substring. Keep a small, tested registry that records:

- tool calling;
- structured output;
- native provider tool search;
- streaming tool calls;
- required integration package;
- any model-specific middleware constraints.

Unknown models default to the portable path. `doctor` explains missing capabilities and packages.

## 6. Pipeboard and tool authorization

### 6.1 Connection

Pipeboard owns ad-platform OAuth and exposes each platform through Streamable HTTP MCP. The host loads
the catalog with `langchain-mcp-adapters` using a bearer token from the environment. The token never
enters the agent state or sandbox.

Each loaded tool becomes a `CatalogEntry` containing the platform, tool name, description, JSON schema,
MCP annotations, source endpoint, catalog revision hash, and local policy classification.

### 6.2 Deny by default

The authorized catalog is the intersection of:

1. the current authenticated Pipeboard catalog;
2. a recognized platform and tool schema;
3. provider `readOnlyHint` or equivalent metadata;
4. the local product deny policy;
5. configured account scope;
6. runtime feature flags.

Missing or malformed mutation metadata is treated as mutation and denied. Direct deletes and generic
raw mutation tools are denied in v1. Catalog counts and remembered names are never runtime evidence.

### 6.3 Context-efficient selection

OpenAI and Anthropic models that pass the explicit capability check use LangChain's
`ProviderToolSearchMiddleware`. All other models use `LLMToolSelectorMiddleware` with a bounded
`max_tools` and a cheap configurable selector model.

Selection is not authorization. Before invocation, trusted code:

- resolves the exact tool name from the current authorized catalog;
- checks platform and account scope;
- validates arguments against the current schema;
- blocks mutation tools from the read dispatcher;
- records the catalog revision and policy decision;
- executes host-side with sanitized errors.

A stale selection, unknown tool, renamed schema, cross-account id, or catalog change fails closed and
asks the agent to discover again.

## 7. Paid-media analysis

### 7.1 Common data model

Normalize provider reads into typed records without erasing platform-specific fields:

```python
class MetricWindow(BaseModel):
    start: date
    end: date
    timezone: str
    is_complete: bool


class PerformanceRow(BaseModel):
    platform: Platform
    account_ref: OpaqueAccountRef
    entity_type: EntityType
    entity_ref: str
    entity_name: str
    window: MetricWindow
    currency: str
    spend: Decimal
    impressions: int | None
    clicks: int | None
    conversions: Decimal | None
    conversion_value: Decimal | None
    source_fields: dict[str, JsonValue]
    quality_flags: tuple[DataQualityFlag, ...]
```

Metrics remain nullable when unavailable. Missing is not zero. Cross-platform totals require a shared
currency, compatible windows, and complete source coverage. Otherwise the report shows per-platform
values and suppresses the total.

### 7.2 Decision workflow

Every recommendation follows:

1. define the business question and decision window;
2. discover current source capability;
3. pull the smallest complete dataset;
4. validate account, window, currency, grain, and row counts;
5. compute metrics and reconciliation in code;
6. compare against the right baseline or target;
7. identify quality and attribution gaps;
8. produce a recommendation with evidence, confidence, expected effect, and reversal plan;
9. create a proposal only when the user asks for a change.

The initial public wiki supplies general decision doctrine, not universal performance thresholds.
Users may add their own goals and targets through host-owned configuration.

### 7.3 Reports

Reports render from a versioned `ReportPayload` through Jinja2 and WeasyPrint. The model writes short
narrative fields; code renders layout, tables, number formats, missing-data states, citations, and
artifacts. The same payload can render to PDF, Slack presentation objects, and UI JSON.

## 8. Governed writes

### 8.1 Domain objects

```python
class ChangeSet(BaseModel):
    proposal_id: UUID
    revision: int
    platform: Platform
    account_ref: OpaqueAccountRef
    tool_name: str
    target_ref: str
    canonical_args: dict[str, JsonValue]
    before: tuple[FieldValue, ...]
    after: tuple[FieldValue, ...]
    reason: str
    risk: RiskLevel
    catalog_revision: str
    payload_digest: str


class ApprovalClaim(BaseModel):
    proposal_id: UUID
    revision: int
    payload_digest: str
    requester_ref: str
    approver_ref: str
    approved_at: datetime
    expires_at: datetime
    nonce: str
    signature: str


class WriteReceipt(BaseModel):
    proposal_id: UUID
    status: Literal["verified", "rejected", "failed", "unknown"]
    mutation_attempted: bool
    provider_operation_ref: str | None
    verified_state: tuple[FieldValue, ...]
    checked_at: datetime
    catalog_revision: str
```

Opaque account and user references are host-resolved. Raw credentials and provider payloads are not
part of these presentation objects.

### 8.2 State machine

```text
draft -> proposed -> awaiting_approval
                      | approve -> executing -> verifying -> verified
                      | edit    -> revised -> awaiting_approval
                      | reject  -> rejected
executing/verifying -> failed | unknown
```

Only the host creates an `ApprovalClaim`. A Slack button or UI action carries an opaque routing id,
not a payload. The host reloads the persisted `ChangeSet`, checks requester and approver policy,
recomputes the digest, verifies freshness and signature, and resolves the current catalog entry before
execution.

Any edit increments the revision and changes the digest. An approval is valid for one proposal
revision, one account, one tool, one requester, one authorized approver, and one bounded time window.

### 8.3 Execution semantics

- Use one mutation attempt. Never blindly retry after a timeout or ambiguous provider response.
- Prefer provider idempotency keys when the exact tool supports them.
- After an ambiguous result, perform read-only reconciliation only.
- Bound readback by count and wall time.
- Return `unknown` when exact state cannot be proven.
- Newly created delivery resources start paused or draft where the provider supports it.
- Activation is a separate proposal and approval.
- Automated tests use constructor-injected fake providers. No environment switch can make a test call
  a live mutation.

## 9. Surfaces

### 9.1 MDA native Slack

The managed profile uses `channels/slack.py` for the simple path: mentions, direct messages, threads,
final responses, and approve or reject interrupts. It is a public-beta convenience layer, not the
source of Slack behavior or write policy.

### 9.2 Rich Slack adapter

The rich adapter uses trusted presentation models and deterministic Block Kit renderers for:

- progress and tool activity;
- report summaries and file delivery;
- proposal review;
- edit, approve, reject, and cancel actions;
- provider receipts and unknown states.

Socket Mode is the zero-public-endpoint local path. Signed HTTP events are the hosted path. Both call
the same application service and use the same replay, dedupe, authorization, and approval rules.

Every Block Kit message includes accessible top-level text. Model text is escaped and bounded. Block
ids, action ids, and button values contain opaque ids only. The renderer enforces Slack limits and
updates one stable message rather than posting uncontrolled progress spam.

### 9.3 Agent UI

The UI reads shared presentation objects and graph state. It may render threads, tool activity,
reports, proposals, interrupts, and receipts. Every UI action has an equivalent agent or API
capability; no business behavior exists only in the UI.

## 10. Runtime profiles and persistence

### Local

- fixture catalog and fake provider by default; the live catalog when credentials are configured;
- local filesystem rooted at the repository, writes only under the workspace;
- in-memory checkpointer; not a production persistence profile;
- used by the demo, the tests, `paid-media-agent ask` and `report`.

### MDA

- root `agent.py` exports one `define_deep_agent` definition;
- project files follow the official MDA layout;
- managed sandbox, threads, checkpoints, schedules, identity, and native Slack are configured through
  project files;
- provider and Pipeboard credentials are deployment secrets;
- rich Slack can remain an external adapter when its UX is required.

### Self-hosted

- compile the same agent components with `create_deep_agent`;
- use the Postgres-backed checkpointer and repositories in production, in-memory only to try;
- expose a small FastAPI boundary for threads, artifacts, approvals, and health;
- use explicit auth (bearer tokens mapped to caller names) and per-caller thread ownership;
- run rich Slack through Socket Mode or signed HTTP;
- ship as one `Dockerfile` and `docker-compose.yml`.

On MDA, proposals, approval claims, and receipts are process-owned objects today; making them
durable across restarts is an open question.

## 11. Sandbox and snapshot

The repository includes a reproducible sandbox recipe and a compatibility checker for an existing
snapshot. The snapshot contains system packages and stable runtime libraries. Instructions, skills,
wiki files, scripts, and templates stay in the repository so they can change without rebuilding the
image.

Sandbox policy:

- workspace path allowlist;
- no `.env`, host home, Docker socket, SSH agent, or cloud metadata access;
- deny outbound network by default;
- allow only explicit documentation or artifact hosts when a task needs them;
- provider and Pipeboard calls remain host-side;
- sanitize archive extraction, paths, filenames, MIME types, and file sizes;
- generated artifacts move through a host-controlled bridge.

The compatibility checker validates Python, required binaries, package versions, writable paths,
network policy, report rendering, and artifact transfer. A compatible user snapshot may be reused;
the included recipe is the reproducible fallback.

## 12. Business wiki and skills

The public wiki covers business goals, channel roles, campaign economics, metrics, attribution,
platform differences, data quality, reporting, experimentation, and write safety. It contains no
vendor-specific private account information.

Initial skills:

- `paid-media-analysis`: question framing, source selection, validation, and recommendation workflow;
- `paid-media-report`: `ReportPayload`, narrative constraints, render script, and templates;
- `paid-media-writes`: when to propose, what reviewers need, and how to handle rejection or unknown
  state;
- `paid-media-onboarding`: fixture demo, Pipeboard connection, account mapping, and doctor checks.

Skills guide judgment. Code grants capability. A skill edit cannot expose a tool, loosen policy, or
authorize a write.

## 13. Target repository layout

The current layout is maintained in [AGENTS.md](AGENTS.md) under "Code shape"; this
specification no longer duplicates it.

## 14. Dependencies

Use Python 3.11+, `uv`, Pydantic v2, current compatible Deep Agents/MDA/LangChain/LangGraph packages,
`langchain-mcp-adapters`, `httpx`, Jinja2, and the Anthropic and OpenAI provider packages (the
managed build installs core only). PDF rendering and other providers remain optional extras.

Commit `uv.lock` after the first working vertical slice. Use explicit upper bounds on fast-moving
pre-1.0 packages, Dependabot or Renovate, and a scheduled compatibility test. Do not hand-maintain two
dependency manifests.

## 15. Tests and evals

### Deterministic tests

- catalog classification and deny policy;
- schema re-resolution and stale-catalog rejection;
- account alias enforcement;
- metric math, date windows, currency, missing values, and reconciliation;
- proposal canonicalization and digest stability;
- approval tamper, expiry, identity, edit, replay, and cross-account rejection;
- one-mutation and bounded-readback semantics;
- Slack Block Kit goldens and accessibility text;
- report payload and rendered-value reconciliation;
- redaction and artifact path safety.

### Real-graph contract tests

Use a scripted model, real Deep Agents graph, checkpointer, middleware, fake Pipeboard catalog, and
fake provider. Test reads, interrupts, resume, edits, rejections, process recovery, and terminal
receipts through the graph. Do not prove HITL by unit-testing a helper in isolation.

### Source-blind evals

Hide implementation details from the evaluated model. Test whether it:

- discovers instead of inventing a tool;
- asks for or reports a missing account/window;
- does not treat missing data as zero;
- cites the evidence file and does not recompute values;
- protects an upstream or pipeline-driving campaign from a shallow last-click conclusion;
- proposes rather than executes;
- explains partial completion and unknown provider state honestly.

### Model matrix

At minimum, test one supported Anthropic model, one supported OpenAI model, and one provider that uses
`LLMToolSelectorMiddleware`. Measure success, tool precision, schema tokens, latency, cost, and
unnecessary calls. Provider-native search and portable selection must produce equivalent authorized
reachability.


## 16. Definition of done

The first public release is done when:

- a clean clone has a one-command fixture demo;
- model configuration is direct and documented;
- Pipeboard connection and account mapping are clear;
- large catalogs remain context-efficient across the model matrix;
- trusted code re-authorizes every selected tool;
- deterministic analysis and reports reconcile;
- all writes are typed, interruptible, durable, exact, and at most once;
- Slack and UI use shared presentation contracts;
- the MDA definition, the self-hosted runtime, and the local CLI use one agent assembly;
- sandbox and secrets boundaries pass rejection tests;
- public docs contain no private data;
- commands, links, install steps, and examples work from a clean environment;
- the license and security contact are explicit.

