# Official engineering contracts

Refreshed: 2026-09-01

## Findings

- Deep Agents exposes a configurable agent harness with model, tools, skills, memory, filesystem,
  permissions, middleware, subagents, HITL interrupts, context, checkpointer, and store.
- MDA uses one root agent entry and project directories for instructions, skills, tools, middleware,
  connectors, sandbox, channels, schedules, identity, memory, and evals.
- MDA is currently public beta on LangSmith Cloud in the US region. Native Slack supports one channel
  and approve/reject HITL. The rich Slack path therefore remains an external adapter.
- LangChain provides `ProviderToolSearchMiddleware` for compatible Anthropic and OpenAI models and
  `LLMToolSelectorMiddleware` as a portable tool filter.
- OpenAI and Anthropic both document deferred tool loading. Support is model-specific, so the product
  needs an explicit tested capability registry.
- Pipeboard publicly exposes hosted MCP connectors and OAuth for multiple ad platforms. The live
  authenticated catalog, not the website, owns current tool schemas.
- Slack Socket Mode supports events and interactivity without a public request URL. Signed HTTP is the
  production alternative for a public endpoint. Block Kit must preserve accessible top-level text.
- Agent Chat UI can connect to local or deployed Agent Server-compatible agents and render tools and
  interrupts. It is an adapter target, not a reason to couple domain state to a frontend.

## Architectural consequence

Use one shared assembly and two thin runtime entries. Keep provider network execution and credentials
host-side. Use framework-supported tool disclosure but independently enforce authorization. Keep rich
Slack outside MDA native Slack while reusing the graph and proposal service.

## Sources

See [official-links.md](../../../sources/official-links.md).

