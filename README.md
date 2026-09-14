<div align="center">
  <p>
    <a href="https://www.langchain.com/">
      <picture>
        <source media="(prefers-color-scheme: dark)" srcset="docs/assets/langchain-company-dark.svg">
        <img src="docs/assets/langchain-company-light.svg" alt="LangChain" width="152">
      </picture>
    </a>
  </p>
  <h1>Paid Media Agent</h1>
  <p>Cross-channel campaign analysis and reporting.<br>Built on <a href="https://github.com/langchain-ai/deepagents">Deep Agents</a>. Deploy with <a href="https://docs.langchain.com/langsmith/python/managed-deep-agents-overview">Managed Deep Agents</a>.</p>
  <p>
    <a href="#quick-start">Quick start</a> ·
    <a href="#deployment">Deployment</a> ·
    <a href="OPERATIONS.md">Documentation</a> ·
    <a href="CONTRIBUTING.md">Contributing</a>
  </p>
</div>

<a href="docs/screenshots/readme-overview-light.png">
  <img src="docs/screenshots/readme-overview-light.png" alt="Paid Media Agent setup console layered with an illustrative Slack report showing spend, leads, cost per lead, and platform comparisons" width="100%">
</a>

<p align="center">
  <sub><a href="docs/screenshots/setup-preview-light.png">Setup console</a> · <a href="docs/screenshots/report-illustration.png">Report illustration</a> with example figures. Presentation varies by runtime.</sub>
</p>

Paid Media Agent helps you understand what changed across your ad accounts and decide what to do
next. Ask questions in Slack or the terminal, generate performance reports, and prepare campaign
changes for review.

It comes with ad platform integrations, analysis and reporting skills, and a paid-media wiki.
Connect your accounts, add your company context, and deploy with
[Managed Deep Agents](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)
or on your own infrastructure. You choose the model.

## What it does

- **Compare campaign performance.** Track spend, conversions, cost per lead, and budget pacing
  across connected accounts.
- **Investigate changes.** Find the campaigns behind a shift, check the supporting data, and flag
  gaps that could change the conclusion.
- **Produce reports.** Generate weekly or monthly summaries with charts, campaign tables, and
  recommendations. Download HTML, or PDF when the host has the rendering libraries installed.
- **Prepare changes for review.** Propose campaign updates with a reason and a plan for checking
  the result.

The model decides what to investigate. Code calculates the metrics and checks report figures
against the source data. Large responses stay in files; the model receives summaries with the
source, date window, and data-quality flags.

**Live ad account changes are off by default.** Enabling them requires a configured write policy,
[release checks](docs/operations/live-write-runbook.md), and approval from an authorized reviewer.
Approval applies to the exact proposal reviewed; editing it requires a new approval.

## Quick start

Requires **Python 3.11+** and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/langchain-ai/paid-media-agent.git
cd paid-media-agent
uv sync
uv run paid-media-agent setup
```

The setup command opens a local console for choosing a model, connecting ad accounts, and
deploying. No frontend build is needed. The CLI exposes the same connection actions with JSON
output if you prefer the terminal.

You can also ask your coding agent to guide setup:

> Read AGENTS.md and .agents/skills/paid-media-onboarding/SKILL.md. Help me connect a model,
> connect my ad accounts, add my business context, and choose a deployment path.

**Try it without model keys or ad accounts:**

```bash
uv run paid-media-agent demo --with-proposal
```

The offline demo runs a scripted analysis and a simulated budget change against synthetic
accounts. It doesn't call a model or touch live campaigns.

Once configured, ask a question or generate a report:

```bash
uv run paid-media-agent ask "Which campaigns had the largest increase in cost per lead last week?"
uv run paid-media-agent report --cadence weekly
```

Questions use your configured model. The `report` command runs without one, using supported
campaign-performance adapters.

## Accounts and business context

Connect the platforms you use:

| Connection | Platforms |
| --- | --- |
| [Pipeboard MCP](https://pipeboard.co/integrations) | Google Ads, Meta Ads, TikTok Ads, Pinterest Ads, Snap Ads, Reddit Ads, LinkedIn Ads, Google Analytics |
| [Direct adapters](OPERATIONS.md#direct-platforms) | X Ads, OpenAI Ads |

Connect any subset. Available tools and metrics depend on platform permissions and API access.
Direct adapters are read-only. Provider data without a supported report mapping can still be
explored through `ask`.

The included [paid-media wiki](workspace/skills/paid-media-wiki/) covers attribution, platform
differences, and budget decisions. Your company context gives the agent the goals, conversion
definitions, and campaign briefs it needs to interpret your performance.

Ask your coding agent to follow the
[business-context skill](.agents/skills/paid-media-org-onboarding/SKILL.md), or create
`workspace/skills/company-context/` yourself using the
[template](docs/customization.md#business-context). Add this context before the first real analysis.

Settings live in `.env`, account mappings in `config/accounts.toml`, and company context in
`workspace/skills/company-context/`. All three are Git-ignored.

## Deployment

Choose who operates the infrastructure:

| | Managed Deep Agents · recommended | Self-hosted |
| --- | --- | --- |
| Hosting | LangSmith manages the runtime and sandbox | You run the API and Postgres |
| Slack | Authorize the managed Slack app | Connect your own Slack app |
| Scheduled reports | Managed weekly and monthly schedules | Run the report command with your scheduler |
| Guide | [Managed deployment](OPERATIONS.md#deploying-with-managed-deep-agents) | [Self-hosting](docs/self-hosting.md) |

For **Managed Deep Agents**, choose **Deploy agent** in setup, or validate and deploy from the terminal:

```bash
uv run paid-media-agent mda check
uv run mda deploy .
```

You'll need a LangSmith organization with MDA access, an API key with deployment permissions,
and a model key. Deployment syncs the instructions and skills, provisions the sandbox, and
configures Slack. Authorize your workspace when prompted. The sandbox snapshot is reused until
its recipe changes. After deployment, open the printed LangSmith URL to inspect your agent.

To **self-host**, install Docker, configure your model and accounts, then generate API credentials
and start the services:

```bash
uv run paid-media-agent config generate PAID_MEDIA_API_TOKENS PAID_MEDIA_APPROVAL_SIGNING_KEY
docker compose up -d --build
```

Compose starts the API and Postgres. Follow the [self-hosting guide](docs/self-hosting.md#connect-slack)
to connect Slack through Socket Mode or signed HTTP. The Docker image includes PDF libraries.

Managed schedules can post text to Slack once you configure a delivery channel. Report files are
available locally and through the self-hosted API. Automatic PDF attachments to Slack are not included.

[Managed hosting is paid](https://www.langchain.com/pricing); model and connector charges depend
on your providers. For local development, `uv run mda dev .` opens the managed runtime in LangSmith
Studio so you can inspect model calls, tool results, and approval requests.

## Build on it

Both deployment paths use the same [agent assembly](src/paid_media_agent/assembly.py), built on
[Deep Agents](https://github.com/langchain-ai/deepagents). It defines the model, tools, middleware,
and approval policy. Extend it without maintaining a separate agent for each interface.

Tools are selected from the connected catalog as needed, limiting how many tool definitions the
model reads on each call. Skills guide the investigation and reporting process; edit them as
Markdown in `workspace/skills/`.

To apply your company's report style, ask your coding agent to update
[DESIGN.md](workspace/skills/report-design/DESIGN.md) and the renderer tokens together. The
[report-design workflow](.agents/skills/paid-media-design/SKILL.md) keeps colors, fonts, and
components aligned across HTML, charts, and PDFs.

Warehouse connections are optional extensions. To bring in pipeline or revenue data, add a
connector and metric mappings to the shared tools. The project doesn't assume a BigQuery, dbt,
or CRM schema. See [optional data sources](docs/customization.md#optional-warehouses-and-dbt).

| Change or explore | Start here |
| --- | --- |
| Business context, memory, and optional data sources | [Customization](docs/customization.md) |
| Agent instructions and paid-media knowledge | [instructions.md](instructions.md) · [workspace/skills/](workspace/skills/) |
| Report colors, typography, and layout | [Report design](docs/customization.md#report-design) |
| Tools and runtime | [src/paid_media_agent/](src/paid_media_agent/) · [Architecture](docs/architecture/README.md) |
| Managed channels and schedules | [channels/](channels/) · [schedules/](schedules/) · [sandbox/](sandbox/) |
| Configuration and troubleshooting | [Operations](OPERATIONS.md) |
| Development and tests | [Contributing](CONTRIBUTING.md) · [Agent instructions](AGENTS.md) · [Coding-agent skills](.agents/skills/) |

Use synthetic data for development. Run `make check` before submitting a change; see
[Contributing](CONTRIBUTING.md) for the development dependencies and checks.

---

[Apache 2.0](LICENSE) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md) · [Code of conduct](CODE_OF_CONDUCT.md)
