# Tools and context

## Catalog lifecycle

1. Load every tool from the eight configured Pipeboard MCP endpoints concurrently, with a
   20-second timeout per endpoint. A failed connector does not discard the others.
2. Normalize schemas and annotations into immutable catalog entries.
3. Apply local platform, mutation, delete, raw-mutate, and account policy.
4. Hash the authorized catalog revision.
5. Expose only a context-efficient selectable surface.
6. Re-resolve and validate the exact current entry immediately before invocation.

A loader retains the catalog in memory for its agent assembly; it does not refetch on each search
or model turn. Rebuild the runtime after credentials change, or explicitly refresh the loader.
Setup actions load a fresh live catalog even when the runtime is currently using sample data.
Account discovery calls independent listing tools concurrently and recognizes ad accounts, TikTok
advertisers, and GA4 properties. Fixture coverage remains Google, Meta, and Reddit.

## Selection paths

`ProviderToolSearchMiddleware` is enabled only by an explicit compatible-model registry. The portable
path uses `LLMToolSelectorMiddleware` with bounded output. Selection tests compare both paths against
the same authorized catalog.

Do not create a third custom search/run mini-protocol unless measured framework behavior cannot meet
the authorization and context budgets. One catalog and two framework-supported disclosure paths are
enough.

## Results

Tool results return typed, bounded summaries. Large rows are written under `workspace/analysis/`.
GA4 and newly connected platforms without verified spend-unit mappings keep their native payloads
as `provider_result` artifacts. They are not coerced into normalized spend comparisons.
Every offloaded artifact records:

- source platform and account alias;
- entity grain;
- requested and actual window;
- row count and schema version;
- quality flags;
- content hash;
- local path.

The model receives no credential-shaped values, raw headers, tokens, internal stack traces, or
unbounded provider payloads.

## Filesystem

The runtime may read wiki and skill files, write analysis artifacts, and render reports. It cannot
read secret files, coding-agent files, original business sources, or paths outside its configured
filesystem root. Runtime skills, including curated company context, are read-only.

## Trusted tool boundary

- `tools/catalog.py` classifies every `RawTool` with `classify()`. Denied reasons are explicit:
  `unknown_platform`, `malformed_schema`, `denied_name_policy`, `missing_mutation_metadata`,
  `destructive_hint`, `no_account_scope`, `mutation_not_admitted`, `duplicate_tool_name`.
- The revision is a hash over qualified name, schema hash, class, reason, and description. A schema
  change on one tool changes both its `schema_hash` and the catalog revision.
- `tools/reads.py` binds one model-facing tool per READ entry. The provider account argument is
  replaced by `account_alias`; the host injects the provider id and rejects any raw id in arguments.
  Arguments are validated with `jsonschema` against the current schema at call time because
  LangChain does not validate dict-form schemas.
- `middleware/authorization.py` hides `task`, `execute`, and `delete` from the model request and
  denies any call outside the assembled surface, so a hallucinated or stale name fails closed.
- `middleware/tool_selection.py` holds the exact-match capability registry. `PortableToolSelectorMiddleware`
  wraps `LLMToolSelectorMiddleware`; a selection that names an unbound tool degrades to core tools
  for that turn instead of aborting the run.
- Live Pipeboard loading (`tools/pipeboard.py`) keeps the bearer token inside the MCP connection map
  and never in state. Tool annotations arrive as LangChain tool metadata; a tool without
  `readOnlyHint` is treated as mutation and denied.

## Direct adapters

Platforms outside Pipeboard live under `tools/direct/`. Each adapter publishes `RawTool` entries
with `readOnlyHint=true` and an account argument, so `build_authorized_catalog` classifies them
with the same policy as MCP tools, and a `CompositeReadProvider` routes execution by platform.
Direct adapters validate identifiers and ISO dates before building any query, bound every HTTP
call, and reduce provider errors to status codes. No direct adapter defines a mutation.
