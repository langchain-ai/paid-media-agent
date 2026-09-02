# Source inventory

## Scope

Sources required to build the open-source Paid Media Agent without importing private company data or
stale framework assumptions.

| Source | Type | Authority | Use | Freshness | Public inclusion |
|---|---|---|---|---|---|
| `SPEC.md` | local contract | binding for this repository | product and acceptance criteria | update with approved scope | yes |
| `docs/architecture/` | compiled local docs | binding for component ownership | runtime and safety boundaries | same change as behavior | yes |
| `docs/business-context/` | compiled public wiki | stable doctrine | analysis judgment and source semantics | source-driven | yes |
| `skills/` | runtime instructions | behavior guidance only | progressive workflows | same change as behavior | yes |
| Deep Agents official docs | external official | framework contract | assembly, middleware, skills, backend, HITL | verify before dependency/API changes | link and summary |
| MDA official docs | external official | managed-runtime contract | project files, deploy, Slack, sandbox, evals | verify before MDA claims | link and summary |
| LangChain middleware docs | external official | middleware contract | provider and portable tool selection | verify before model matrix | link and summary |
| OpenAI tool-search docs | external official | OpenAI API contract | native deferred loading | verify before OpenAI support claim | link and summary |
| Anthropic tool-search docs | external official | Anthropic API contract | native deferred loading | verify before Anthropic support claim | link and summary |
| Pipeboard public docs | external vendor | product-level contract | endpoints, OAuth, public platforms | verify before release | link and summary |
| Live Pipeboard catalog | authenticated runtime | current capability authority | exact schemas and annotations | query-time | never commit raw private catalog |
| Slack official docs | external official | Slack transport/UI contract | Socket Mode, signed HTTP, Block Kit | verify before Slack release | link and summary |
| Existing private paid-media implementation | local reference | evidence, not public truth | extract general architecture lessons | point-in-time | no code, fixtures, ids, or private history copied |

## Exclusions

- private Slack, Notion, Linear, CRM, warehouse, or production traces;
- connected account ids, campaign names, spend, budgets, thresholds, or customer data;
- copied vendor tool catalogs containing private connection metadata;
- secrets, tokens, cookies, screenshots with private values, or production errors;
- internal company brand assets or report copy.

## Conflict handling

The live authenticated catalog wins for current connected capability. Official vendor docs win for
external contracts. Repository tests win for implemented behavior. The compiled wiki wins only for
stable doctrine. Record unresolved conflicts in `open-questions.md`.

