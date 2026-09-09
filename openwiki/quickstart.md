---
type: "Reference"
title: "Paid Media Agent: Change-Oriented Quickstart"
openwiki_generated: true
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T17:45:08.888Z
sources:
  - id: openwiki-source-eca60e2ced68ba99bd0ac710
    resource: repo://agent.py
  - id: openwiki-source-e27f6097e5ac616e489a6925
    resource: repo://docs/architecture/writes-and-approvals.md
  - id: openwiki-source-7aefb61d4a8d05861dff7097
    resource: repo://OPERATIONS.md
  - id: openwiki-source-065880814c34af88b680e507
    resource: repo://src/paid_media_agent/assembly.py
  - id: openwiki-source-faafad77ccc57d40950c3059
    resource: repo://src/paid_media_agent/runtime/local.py
  - id: openwiki-source-a6ab0794cca0579401d348ab
    resource: repo://src/paid_media_agent/runtime/mda.py
  - id: openwiki-source-a9c4227376c43c4bb9637b5c
    resource: repo://tests/contract/test_live_write_gates.py
  - id: openwiki-source-00870ce0f2d2cecd69af1e73
    resource: repo://tests/contract/test_surfaces_and_runtimes.py
  - id: openwiki-source-64e4ca3225bd2233888a6c5b
    resource: repo://tests/contract/test_write_flows_graph.py
generated: { by: "openwiki/0.5.0", at: "2026-09-09T17:45:08.888Z" }
---


# Paid Media Agent: Change-Oriented Quickstart

This is a routing page, not a replacement for the human-reviewed architecture contract or the code and tests. The repository has **one shared agent assembly**: `agent.py` builds Managed Deep Agents from `build_mda_components`, while local execution compiles the same assembled components into a Deep Agents graph. Do not fork tools, middleware, policy, or business logic for a surface or runtime adapter. [Shared Agent Assembly and Runtime Boundaries](architecture/shared-agent-runtime.md) is the owning explanation. [AGENTS.md](repo://AGENTS.md#L22-L45) and [the architecture index](repo://docs/architecture/README.md#L15-L27) state this as a binding invariant; the MDA and local implementations show the two compilation boundaries.

A provider mutation is never a model-bound raw tool call. The safe path is a typed proposal, persisted approval, exact validation, one mutation attempt, bounded readback, and a terminal receipt; revising a proposal changes its digest and invalidates earlier approval. Start any change touching proposals, approvals, write tools, provider mutations, or reviewer UI at [Governed Change and Approval Protocol](concepts/governed-write-protocol.md).

## First 15 minutes

1. Read [README.md](repo://README.md#L27-L59), then run the offline fixture path:

   ```bash
   uv sync --all-extras --dev
   uv run paid-media-agent demo --with-proposal
   ```

   Python 3.11+ is required, and `paid-media-agent` is the installed CLI entry point.
2. Read [AGENTS.md](repo://AGENTS.md#L6-L14) in its prescribed order: architecture, the runtime business skill, the behavior-specific skill, the owning module and tests, then operations. Link to the [paid-media business wiki](repo://skills/paid-media-wiki/SKILL.md); do not duplicate its business doctrine here.
3. Read [Shared Agent Assembly and Runtime Boundaries](architecture/shared-agent-runtime.md), then use the routing table below to identify the narrowest owner for the requested change.
4. Make the smallest root-cause change, add a focused test that covers its critical failure path, and run the narrowest relevant checks first. Do not run live mutations in automated tests.

## Non-negotiable change boundaries

| Boundary | What it means for a change | Owning page |
|---|---|---|
| Shared assembly | `agent.py`, local CLI, schedules, and delivery surfaces adapt one component set rather than maintaining separate graphs or policies. | [Shared Agent Assembly and Runtime Boundaries](architecture/shared-agent-runtime.md) |
| Host-owned authorization | Catalog admission, account aliases, schemas, invocation checks, result limits, and redaction are trusted host controls; unknown or malformed tools fail closed. | [Authorized Tool Catalog, Reads, and Analysis Artifacts](concepts/authorized-catalog-and-read-data.md) |
| Governed writes | The model proposes; persisted, scoped human approval authorizes an exact revision; the executor, not a surface, mutates once and readbacks. | [Governed Change and Approval Protocol](concepts/governed-write-protocol.md) |
| Deterministic reporting | The model investigates and explains; code owns arithmetic, reconciliation, windows, and rendered report layout. | [Analysis and Deterministic Reporting Workflow](workflows/analysis-and-reporting.md) |
| Hosted context | MDA gives each thread a sandbox. It syncs skills, not the repository; organization data and host artifacts cross through explicit tools. | [Sandbox Snapshots and Hosted Context Boundary](operations/sandbox-and-hosted-context.md) |

## Route by the behavior you are changing

| If the request involves… | Read first | Then inspect |
|---|---|---|
| Agent graph composition, runtime parity, middleware order, model selection, filesystem access, or MDA vs local behavior | [Shared Agent Assembly and Runtime Boundaries](architecture/shared-agent-runtime.md) | `agent.py`, `src/paid_media_agent/assembly.py`, `src/paid_media_agent/runtime/mda.py`, `src/paid_media_agent/runtime/local.py` |
| Tool discovery, Pipeboard/direct-tool admission, account scope, schema validation, offload, or deterministic analysis | [Authorized Tool Catalog, Reads, and Analysis Artifacts](concepts/authorized-catalog-and-read-data.md) | [Advertising Platform Integrations and Catalog Admission](integrations/advertising-platforms-and-pipeboard.md) |
| A requested change, review card, interrupt, approval/rejection, revision, execution, receipt, or live-write release | [Governed Change and Approval Protocol](concepts/governed-write-protocol.md) | [Proposal Review Across Graph and Surfaces](workflows/proposal-review-and-execution.md) |
| Period comparisons, scheduled/local reports, quality flags, reconciliation, or HTML/PDF output | [Analysis and Deterministic Reporting Workflow](workflows/analysis-and-reporting.md) | [Local Setup, CLI, Console, and Managed Deployment](operations/local-setup-and-managed-deployment.md) |
| `.env`, onboarding, CLI/console behavior, `doctor`, MDA development/deployment, schedules, or incident switches | [Local Setup, CLI, Console, and Managed Deployment](operations/local-setup-and-managed-deployment.md) | [Sandbox Snapshots and Hosted Context Boundary](operations/sandbox-and-hosted-context.md) |
| A regression plan, contract boundary, evaluation, browser flow, or opt-in provider check | [Verification Strategy and Safety Contracts](testing/verification-strategy.md) | The nearest `tests/unit`, `tests/contract`, `tests/behavior`, or `tests/integration` test |

## Assembly orientation

`build_agent_components` is the policy seam. It constructs host services, binds core/read/write tools, admits write tools only for the conversational runtime, creates a single allowed tool surface, selects a provider-native or portable tool-selection path, and orders retry/timeout, date, selection, invocation guard, offload, and redaction middleware. Only `execute_change` receives the approval interrupt. The component object deliberately carries the proposal service, write executor, and read dispatcher so callers can reuse the same host services rather than reconstructing them.

The configured profile loads a live catalog only when credentials are available; otherwise it uses fixtures. Local `ask` and `report` use that configured profile, while MDA owns the surrounding hosted concerns such as checkpointing, thread sandbox, identity, schedules, and Slack. Local compilation instead uses an in-memory checkpointer and a virtual repository filesystem with secrets and tooling paths denied and writes confined to `/workspace`.

## Write-change checklist

Before changing any mutation-capable path, trace the protocol end-to-end in [Governed Change and Approval Protocol](concepts/governed-write-protocol.md) and preserve these properties:

- Keep raw provider mutation operations out of the model-facing tool list; proposal and execution are the controlled entry points.
- Treat approvals as identity-, thread-, proposal-revision-, digest-, expiry-, and single-use-bound claims, not as UI state or a prompt instruction.
- Recheck the current catalog/schema and write policy when executing; a stale or altered proposal must not execute.
- Never retry a provider mutation. Reconcile uncertainty with bounded readback and return a receipt that can be `verified`, `failed`, `rejected`, or `unknown`.
- For live providers, retain the kill switch plus the enabled flag, pinned catalog revision, and canary tool allowlist. Fixture behavior is not permission to relax live gates.

The real-graph tests demonstrate the expected interruption, approval, single mutation, readback, rejection, and uncertainty behavior. In particular, they prove that tampering, revision after approval, expiry, replay, foreign identity/account, stale catalog/policy, and disabled live gates leave the provider untouched.

## Operations and verification handoff

Use `OPERATIONS.md` before running, releasing, changing dependencies, connecting accounts, publishing snapshots, or deploying. The setup console and CLI invoke the same actions, but the console is local-only and is not a hosted administration surface. Default tests are offline; live integration checks are opt-in and must remain read-only.

For a broad repository health check after focused validation:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest -q
```

For hosted-context changes, verify the sandbox boundary separately: MDA synchronizes `instructions.md` and `skills/`, while the deployed model sees `/skills` and its per-thread `/workspace`, not the checkout. Do not put secrets, private organization data, or raw provider payloads into prompts, sandbox files, fixtures, logs, artifacts, or tests.

## Evidence-backed starting points

- The root MDA entry is intentionally thin: it creates settings and shared MDA components, then passes their model, tools, middleware, and interrupts to `define_deep_agent`. [agent.py](repo://agent.py#L1-L21)
- The shared assembly is where services and tools are constructed, the allowed surface is established, and middleware and the `execute_change` interrupt are configured. [assembly.py](repo://src/paid_media_agent/assembly.py#L115-L145) [assembly.py](repo://src/paid_media_agent/assembly.py#L181-L285)
- The MDA profile uses the live catalog only when available and otherwise fixtures; the local configured runtime compiles that same profile without loosening the write gate. [mda.py](repo://src/paid_media_agent/runtime/mda.py#L45-L74) [local.py](repo://src/paid_media_agent/runtime/local.py#L110-L132)
- The architecture contract defines deny-by-default authorization, deterministic computation, host-owned account identity, and exact approval with one attempt plus bounded readback. [docs/architecture/README.md](repo://docs/architecture/README.md#L15-L27)
- Contract tests verify MDA’s shared assembled components and configured local profile, and exercise governed-write failure modes including no retry after uncertain provider outcomes. [test_surfaces_and_runtimes.py](repo://tests/contract/test_surfaces_and_runtimes.py#L110-L156) [test_write_flows_graph.py](repo://tests/contract/test_write_flows_graph.py#L45-L72) [test_write_flows_graph.py](repo://tests/contract/test_write_flows_graph.py#L106-L187) [test_write_flows_graph.py](repo://tests/contract/test_write_flows_graph.py#L281-L307) [test_live_write_gates.py](repo://tests/contract/test_live_write_gates.py#L75-L167)
