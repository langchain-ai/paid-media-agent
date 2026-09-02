# Engineering-source log

## 2026-09-01

- Verified current Deep Agents customization and MDA project structure, agent definition, deployment,
  and Slack documentation.
- Verified LangChain provider tool search and portable LLM tool selector middleware.
- Verified OpenAI and Anthropic deferred tool-search documentation.
- Verified Pipeboard's public MCP integration surface and Slack Socket Mode/Block Kit contracts.
- Verified Claude Fable 5.1 prompting guidance used by `IMPLEMENTATION_PROMPT.md`.

## 2026-09-01 (implementation)

- Verified in the installed environment: `deepagents` 0.7.12 `create_deep_agent` middleware ordering
  and `HumanInTheLoopMiddleware` decision contract; `managed-deepagents` 0.6.1 `define_deep_agent`,
  `channels.slack()`, `define_sandbox()`; `langchain` 1.3.18 `ProviderToolSearchMiddleware`
  (anthropic `tool_search_tool_bm25_20251119`, openai `tool_search`) and `LLMToolSelectorMiddleware`;
  `langchain-mcp-adapters` 0.3.2 `StreamableHttpConnection` and annotation-to-metadata mapping.
- Confirmed from current provider docs: Anthropic tool search on Claude 4.5+ models, OpenAI
  `tool_search` on gpt-5.4 and later. The capability registry lists only those exact model ids.
- Found that LangChain returns dict-form tool arguments unvalidated; the host validates with `jsonschema`.
