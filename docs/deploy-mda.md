# Deploy with Managed Deep Agents

Managed Deep Agents (MDA) runs the agent, a sandbox for every thread, its Slack app, its schedules,
and its background helpers in your LangSmith workspace, with tracing built in. This repository is
an MDA project, so it deploys as it is. Run these in your own terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/langchain-ai/paid-media-agent/main/install.sh | bash
cd paid-media-agent
uv run paid-media-agent config set LANGSMITH_API_KEY ANTHROPIC_API_KEY PIPEBOARD_API_TOKEN
uv run paid-media-agent accounts discover --add
uv run paid-media-agent mda deploy --yes
```

The installer gets [uv](https://docs.astral.sh/uv/) if you don't have it, clones the repository,
and installs its dependencies; `git clone` and `uv sync` do the same. `uv run` uses the `mda` CLI
pinned in `uv.lock`, so the CLI matches the SDK the agent is built on. The steps below explain each
command.

## What you need

- A LangSmith Cloud account with Managed Deep Agents (US region) and a personal access token.
  [Hosting is paid](https://www.langchain.com/pricing).
- A key for your model. The default is `anthropic:claude-opus-5-5`; on the LangSmith Gateway, set
  `PAID_MEDIA_MODEL=langsmith:anthropic/claude-opus-5-5` and skip the provider key
  ([Models](../OPERATIONS.md#models)).
- A [Pipeboard](https://pipeboard.co/pricing) account for Google, Meta, LinkedIn, TikTok,
  Pinterest, Snap, Reddit Ads, and Google Analytics. Its free plan covers 2 ad accounts and 30
  tool runs a week; paid plans start at US$29.90 a month. X Ads and OpenAI Ads connect directly
  ([Direct platforms](../OPERATIONS.md#direct-platforms)).
- Python 3.12+ and [uv](https://docs.astral.sh/uv/). `uv sync` fetches a matching Python.

## 1. Keys

```bash
uv run paid-media-agent config set LANGSMITH_API_KEY ANTHROPIC_API_KEY PIPEBOARD_API_TOKEN
```

Naming a key without `=VALUE` asks for it in your terminal without echoing it. Enter keeps the
current value. Never paste a key into a chat; a coding agent should ask you to run this yourself.
The setup console (`uv run paid-media-agent setup`) saves the same keys.

- `LANGSMITH_API_KEY` is a personal access token (`lsv2_pt_...`) from LangSmith's API Keys page.
  A service key (`lsv2_sk_...`) cannot set up the Slack channel. Without a key, deploy asks you to
  sign in with your browser. Set `LANGSMITH_WORKSPACE_ID` when the key reaches more than one
  workspace.
- `PIPEBOARD_API_TOKEN`: connect your ad platforms in Pipeboard, then create a token under
  **Settings → API Tokens → Generate Token**.

## 2. Ad accounts

```bash
uv run paid-media-agent test pipeboard
uv run paid-media-agent accounts discover --add
```

`test pipeboard` loads each connected platform's tools. `accounts discover --add` lists every ad
account the token reaches and maps each new one to an alias such as `google-acme-search` in
`config/accounts.toml`. The agent only ever sees aliases. To choose aliases yourself, run
`accounts discover`, then `accounts add <alias> --platform <platform> --id <id>` (with
`--currency` and `--timezone` when not USD and UTC). `accounts remove <alias>` drops one.

Add your goals, conversion definitions, and campaign conventions before the first real analysis:
ask your coding agent to follow the
[`paid-media-org-onboarding` skill](../.agents/skills/paid-media-org-onboarding/SKILL.md).

## 3. Check

```bash
uv run paid-media-agent mda check
```

It exits non-zero while anything blocks the deploy and names the variable to set. Read its
warnings: it says when the deployed agent would answer from synthetic demo data (no platform
connected), when only X or OpenAI Ads is connected (live data mixed with demo data), when
`config/accounts.toml` is missing, when the LangSmith key cannot set up Slack, and which local files
a plain `mda deploy` would upload.

## 4. Deploy

```bash
uv run paid-media-agent mda deploy --yes
```

It runs the check, then `mda deploy` on a copy of the project without the local working folders
(`workspace/analysis`, `in`, `logs`, `out`, `sessions`, and `sources`). MDA does not read
`.gitignore`, so a plain `uv run mda deploy` would upload them. Expect several minutes: the image
build and, on a first deploy or a changed `sandbox/setup.sh`, the sandbox bake. MDA bakes the
sandbox itself; there is no separate publish step.

**Run the first deploy in your own terminal.** Deploy may ask, in order:

1. for a LangSmith key or a browser sign-in, when `LANGSMITH_API_KEY` is not set;
2. which Slack app to use: one LangSmith creates and manages (recommended), a new one from a
   manifest, or your own (`MDA_SLACK_BOT_TOKEN` and `MDA_SLACK_SIGNING_SECRET`, read by the CLI
   only);
3. to authorize LangSmith in Slack or install the app: it prints a link and waits up to an hour for
   Slack to report it done. A workspace admin may have to approve the app.

Without a terminal, deploy can only use a LangSmith-managed app in a Slack workspace you have
authorized before; otherwise it stops before uploading and says to run it in a terminal once. Later
deploys ask nothing. `uv run mda channels setup` in a terminal checks or finishes the Slack setup
without deploying.

## 5. First question

In Slack, find the app under **Apps** (named by `PAID_MEDIA_SLACK_NAME`, "Paid Media Agent" by
default) and send it a direct message, or `/invite` it to a channel and mention it once: in a
thread it keeps answering without another mention. Try:

> How did spend and conversions change last week across my accounts?

Each step shows above the reply while it works, and the reply ends with minutes taken and an
estimated cost. If nothing comes back, read `uv run mda logs --no-follow`, and the run's trace in
the LangSmith deployment the deploy printed.

## What ships

The deploy uploads the code, `instructions.md`, the runtime skills (synced to Context Hub), your
Git-ignored `config/accounts.toml`, `config/write-policy.toml`, and
`workspace/skills/company-context/`, the Slack icon, the sandbox recipe, and the MDA declarations
(`agent.py`, `identity.py`, `channels/`, `schedules/`, `sandbox/`). It leaves out `.env`, virtual
environments, caches, and the local working folders above.

Every set value in `.env` becomes a deployment secret, except LangSmith's own deploy key. Keep
`.env` to what the deployed agent uses: the model key, `PIPEBOARD_API_TOKEN` or the X and OpenAI
Ads keys, and `PAID_MEDIA_*` settings. Leave the self-hosted values blank: `SLACK_BOT_TOKEN`,
`SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`, `DATABASE_URL`, and `PAID_MEDIA_API_TOKENS`.

## Day to day

| Command | Purpose |
| --- | --- |
| `uv run paid-media-agent mda deploy --yes` | Ship your changes (instructions, skills, context, accounts, code) |
| `uv run paid-media-agent mda deploy --yes --name paid-media-agent-test` | Deploy a separate copy to test changes |
| `uv run mda dev` | Run the agent locally in LangSmith Studio |
| `uv run mda logs --no-follow` | Read the deployed agent's recent logs |
| `uv run mda channels setup` | Check or finish the Slack setup without deploying |
| `uv run mda delete --name <name>` | Remove a deployment, its sandboxes, and its snapshot |

`mda deploy` creates a **serverless** deployment by default, which can scale to zero. Proposals and
approvals in the MDA profile are process-local ([Writes](../OPERATIONS.md#writes)), so a scale-down
between a proposal and its approval loses the proposal and the approval is refused. That fails
closed, but the change has to be proposed again. Before enabling live writes, deploy with
`--deployment-type dedicated`. Existing deployments keep their type.

In MDA 0.10, `LANGSMITH_API_KEY`, `LANGSMITH_ENDPOINT`, and `LANGSMITH_WORKSPACE_ID` come from
your shell first and the project `.env` second; unset a stale shell value if deploy targets the
wrong workspace. A local check does not prove your cloud permissions; the deployment status and a
real answer in Slack do.
