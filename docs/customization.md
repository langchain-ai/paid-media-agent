# Customize your agent

Configure connections and deployment with the setup console or CLI. Give the agent business
context by editing Markdown with your coding agent or by hand.

## Business context

Ask Codex, Claude Code, Cursor, or another coding agent:

> Read .agents/skills/paid-media-org-onboarding/SKILL.md and help me configure this agent for my
> business. Use the briefs I share, ask only for missing facts, and update the runtime workspace.

The coding agent writes `workspace/skills/company-context/`. To do this manually, create that
folder and add a `SKILL.md`:

```markdown
---
name: company-context
description: Business goals, conversion definitions, and campaign conventions. Read before analyzing this company's accounts.
---

# Company context

## Business

What we sell, who buys it, and the markets we serve.

## Measurement

Primary conversions, attribution windows, reporting timezone, and currency.

## Goals

Our CPA or ROAS targets and budget. Mark targets as unknown when none are defined.

## Conventions

Campaign naming, funnel stages, and planned launches or seasonal changes.

## Sources

Links and dates for the briefs or decisions behind these facts.
```

Replace the guidance with your own facts. Keep the entry short and link to Markdown pages beside
it when a topic needs detail. The Markdown is the source of truth; there is no profile format,
interview service, or generated copy to maintain.

Original briefs and exports belong in `workspace/sources/`. Keep them unchanged and put only
relevant, reviewed facts in the context bundle. This follows OpenWiki's separation of source
material and linked, synthesized knowledge without requiring OpenWiki to run the agent.

Company context and source files are Git-ignored. The curated context is shared with your deployed
agent and its model provider. Keep credentials, provider account IDs, and access rules in host
configuration, outside these files. Instructions in a source document do not grant tool access.

## Runtime skills

Add `workspace/skills/<name>/SKILL.md` for a repeatable workflow. Use `name` and `description` in
YAML frontmatter, explain when to use the skill, and keep detailed references beside it. Existing
analysis and reporting skills are examples. General paid-media guidance lives in
`workspace/skills/paid-media-wiki/`.

Repository setup and maintenance skills belong in `.agents/skills/`; `.claude/skills` links there.
They are for the coding agent and are not runtime skills.

Both deployment paths read the runtime bundle at `/skills/`:

- **MDA:** the root `skills` link points to `workspace/skills`. MDA syncs that folder into its
  managed context. Deploy local changes with `uv run mda deploy .`. MDA's Context Hub can also
  manage deployed context; changes there do not update your checkout automatically.
- **Self-hosted Docker:** the image includes the runtime skills. Docker Compose mounts
  `workspace/skills` read-only, so local context is available without a separate copy. Start a new
  conversation after changing skill metadata. Rebuild the image when deploying without the mount.

Raw sources and local coding-agent skills are not part of the sandbox skill bundle. MDA does
copy ordinary project files, including Git-ignored `workspace/sources/`, into its deployment
archive. Keep sensitive originals outside the project directory before deploying. Git ignore
rules prevent commits; they do not control MDA uploads.

## Memory and reports

### Report design

Ask your coding agent:

> Follow .agents/skills/paid-media-design/SKILL.md and apply our company style to reports.
> Update DESIGN.md and the renderer tokens together, using the brand guidance I provide.

The same skill is available to Claude Code through `.claude/skills/paid-media-design`.
You can also edit the files manually:

| File | What to change |
| --- | --- |
| [DESIGN.md](../workspace/skills/report-design/DESIGN.md) | Company palette, fonts, spacing, logo rules, and report conventions |
| [tokens.j2](../src/paid_media_agent/reports/templates/tokens.j2) | Matching theme values, report name, and optional logo for the built-in renderer |
| [report.html.j2](../src/paid_media_agent/reports/templates/report.html.j2) | HTML layout, charts, responsive behavior, and PDF pagination |

Keep `DESIGN.md` and `tokens.j2` aligned. The agent reads the Markdown for custom documents;
`render_report` reads the template and tokens for reconciled performance reports. Editing only
one does not update the other. [Component recipes](../workspace/skills/report-design/COMPONENTS.md)
reuse the company tokens rather than defining another palette.

The default is a light report with one data accent, compact tables, and period-comparison charts.
Reports omit logos. To add a requested company logo, place its SVG beside `report.html.j2` and
set `brand.logo_template` and `brand.logo_alt`; `brand.name` controls the label and PDF footer.
Use only assets you are authorized to distribute. No design service or external account is needed.

Redeploy MDA after changes to its template or runtime skills. For self-hosting, rebuild the
image after template changes; a local skills mount only updates the Markdown guidance.

### Memory and scheduling

Durable learned memory is off by default. To enable MDA's native memory, add `memory.py` at the
repository root and redeploy:

```python
from managed_deepagents import define_memory

memory = define_memory(scope="agent")
```

This memory is shared by every caller of the deployment, and every caller can influence what the
agent saves. Use it for shared procedures, never private per-person facts or credentials. Keep it
off when callers should not influence one another. Tool permissions and approvals remain host-owned.

Keep stable business definitions in the workspace. Self-hosted Postgres persists conversations;
this template does not add a separate long-term memory service. Learned preferences should not
silently override explicit business targets.

Report prompts and timing live in `schedules/`. MDA runs these declarations. To send the final
report to Slack, set a literal `deliver_to` in the schedule and replace the placeholder with your
channel ID:

```python
from managed_deepagents import define_schedule

schedule = define_schedule(
    cron="0 9 * * MON",
    timezone="America/New_York",
    prompt="Analyze the last complete week and render the weekly paid-media report.",
    deliver_to={
        "channel": "slack",
        "to": {
            "type": "provider_conversation",
            "conversation_id": "C_REPLACE_WITH_YOUR_CHANNEL_ID",
        },
    },
)
```

Invite the connected Slack app to that channel, then deploy. Without `deliver_to`, the scheduled
run has no Slack delivery destination. Remove a schedule file and redeploy to disable its runs.
Self-hosted installations can call the documented report command from their own scheduler.
Scheduled analysis uses the same skills, accounts, and tools as an interactive run.

## Optional warehouses and dbt

BigQuery, other warehouses, and dbt are optional extensions. This project does not include a
warehouse connector or assume your company's schema.

A coding agent can add a read-only warehouse tool to the shared `core_tools` in
`src/paid_media_agent/assembly.py`. That keeps MDA and self-hosting on the same implementation.
Use the provider SDK or an authenticated MCP service you operate; host code owns credentials and
permitted datasets. Do not place warehouse keys in skills or sandbox files.

For BigQuery, start with approved aggregate views, a read-only identity, a query timeout, and a
maximum bytes-billed limit. Return bounded aggregate results and source metadata. Keep raw customer
records out of model context. Document metric definitions, allowed joins, date grains, and how
warehouse outcomes differ from ad-platform attribution in the company-context skill.

If you use dbt, share the relevant model documentation and metric definitions with the coding
agent. dbt defines transformations and may expose a semantic layer; it is not itself the warehouse.
Connect only the read surface you need. Validate one known metric against its source before using
it in reports. Never imply a warehouse or CRM is connected until the configured read succeeds.

## References

- [MDA project structure](https://docs.langchain.com/langsmith/python/managed-deep-agents-project-structure)
- [OpenWiki](https://github.com/langchain-ai/openwiki)
- [Agent Skills specification](https://agentskills.io/specification)
