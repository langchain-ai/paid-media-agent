# Official engineering sources

Refresh these links before changing an external contract. Record material changes in `log.md` and the
owning architecture page.

## Deep Agents and MDA

- [Customize Deep Agents](https://docs.langchain.com/oss/python/deepagents/customization)
- [Deep Agents human-in-the-loop](https://docs.langchain.com/oss/python/deepagents/human-in-the-loop)
- [Managed Deep Agents overview](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
- [MDA project structure](https://docs.langchain.com/langsmith/python/managed-deep-agents-project-structure)
- [MDA agent definition](https://docs.langchain.com/langsmith/python/managed-deep-agents-agent-definition)
- [MDA custom tools](https://docs.langchain.com/langsmith/python/managed-deep-agents-tools)
- [MDA custom middleware](https://docs.langchain.com/langsmith/python/managed-deep-agents-middleware)
- [MDA Slack channel](https://docs.langchain.com/langsmith/python/managed-deep-agents-channels-slack)
- [MDA deployment](https://docs.langchain.com/langsmith/python/managed-deep-agents-deploy)

Current documented boundary: MDA is a public beta on LangSmith Cloud in the US region. A project has
one required root `agent.py`; instructions, skills, tools, middleware, connectors, sandbox, identity,
channels, schedules, and evals are project files. The managed Slack channel supports one Slack channel
and approve/reject HITL decisions. Recheck these limits at implementation and release time.

## Models and tool disclosure

- [LangChain prebuilt middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in)
- [OpenAI tool search](https://developers.openai.com/api/docs/guides/tools-tool-search)
- [OpenAI tools overview](https://developers.openai.com/api/docs/guides/tools)
- [Anthropic tool search](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-search-tool)
- [Anthropic tool reference](https://platform.claude.com/docs/en/agents-and-tools/tool-use/tool-reference)

LangChain documents `ProviderToolSearchMiddleware` for supported Anthropic and OpenAI models and
`LLMToolSelectorMiddleware` as the portable model-based filter. The provider docs define the actual
deferred-loading contracts. Keep the repository capability registry narrower than or equal to those
current contracts.

## Pipeboard

- [Pipeboard integrations](https://pipeboard.co/integrations)
- [Pipeboard MCP product](https://pipeboard.co/products/mcps)
- [Pipeboard Google integration and permissions](https://pipeboard.co/google-mcp)
- [Pipeboard API tokens](https://pipeboard.co/api-tokens)
- [Pipeboard connections](https://pipeboard.co/connections)
- [TikTok Ads MCP](https://pipeboard.co/guides/tiktok-ads-mcp)
- [Pinterest Ads MCP](https://pipeboard.co/guides/pinterest-ads-mcp)
- [Snap Ads MCP](https://pipeboard.co/guides/snap-ads-mcp)
- [Google Analytics MCP](https://pipeboard.co/guides/google-analytics-mcp)
- [LinkedIn Ads MCP](https://pipeboard.co/guides/linkedin-ads-mcp)

Pipeboard's public pages establish its MCP and OAuth product surface. Only the authenticated live
catalog establishes the exact tools and annotations available to a configured user.

## Slack and UI

- [Slack Socket Mode](https://docs.slack.dev/apis/events-api/using-socket-mode/)
- [Slack Bolt for Python Socket Mode](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/)
- [Slack Block Kit](https://docs.slack.dev/block-kit/)
- [Slack request verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
- [LangChain Agent Chat UI](https://docs.langchain.com/oss/python/langchain/ui)

Socket Mode removes the need for a public event URL but is not eligible for the public Slack
Marketplace. Signed HTTP events are the hosted alternative. Block Kit content must include an
accessible top-level message.

## Fable 5.1 execution prompt

- [Claude Fable 5.1](https://www.anthropic.com/claude/fable)
- [Prompting Claude Fable 5.1](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/prompting-claude-fable-5-1)
- [Claude prompting best practices](https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices)

The implementation prompt applies current guidance on clear scope, full-task completion, concise
progress, parallel independent tool calls, targeted edits, bounded extras, and explicit verification.

