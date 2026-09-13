"""Onboarding routes: ordered steps whose status is derived from the current host state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import JsonValue

StepStatus = Literal["done", "todo", "optional", "blocked"]
ActionKind = Literal["form", "test", "run", "process", "link", "command", "accounts"]


class StepAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    label: str
    keys: tuple[str, ...] = ()
    """Env keys a `form` action edits."""
    action: str = ""
    """Server action name for `test`, `run`, `process`, `accounts`."""
    href: str = ""
    payload: dict[str, JsonValue] = Field(default_factory=dict)


class Step(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    description: str
    status: StepStatus
    cli: str
    action: StepAction | None = None
    note: str = ""


class Route(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    tagline: str
    description: str
    steps: tuple[Step, ...]

    @property
    def done(self) -> int:
        return sum(1 for s in self.steps if s.status == "done")


def _get(detail: dict[str, JsonValue], *path: str) -> JsonValue:
    node: JsonValue = detail
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node


def build_routes(detail: dict[str, JsonValue]) -> list[Route]:
    env = _get(detail, "env") or {}
    model = _get(detail, "model") or {}
    slack = _get(detail, "slack") or {}
    mda = _get(detail, "mda") or {}
    self_hosted = _get(detail, "self_hosted") or {}
    writes = _get(detail, "writes") or {}
    accounts = _get(detail, "accounts") or []
    token_set = bool(_get(detail, "pipeboard", "token_set"))
    model_ready = bool(model.get("package_installed")) and bool(_get(detail, "model_key_set"))
    direct_keys = {
        "x": (
            "X_ADS_CONSUMER_KEY",
            "X_ADS_CONSUMER_SECRET",
            "X_ADS_ACCESS_TOKEN",
            "X_ADS_ACCESS_TOKEN_SECRET",
        ),
        "openai_ads": ("OPENAI_ADS_API_KEY",),
    }
    direct_set = {
        name: all(isinstance(env, dict) and env.get(k) for k in keys)
        for name, keys in direct_keys.items()
    }
    accounts_path = str(_get(detail, "accounts_path") or "")
    real_accounts = accounts_path.endswith("config/accounts.toml")
    snapshot = str(env.get("PAID_MEDIA_SANDBOX_SNAPSHOT") or "") if isinstance(env, dict) else ""

    local = Route(
        id="local",
        title="Model & testing",
        tagline="Test your agent locally",
        description="Configure a model, try sample campaigns, and run reports from your terminal.",
        steps=(
            Step(
                id="tooling",
                title="Install dependencies",
                description="Install the Python packages this project needs. Requires Python 3.11 or later and uv.",
                status="done" if _get(detail, "tooling", "uv") else "todo",
                cli="uv sync --all-extras --dev",
            ),
            Step(
                id="demo",
                title="Try sample campaigns",
                description="Compare spend and conversions using sample ad accounts. No API key needed.",
                status="todo",
                cli="uv run paid-media-agent demo --with-proposal",
                action=StepAction(
                    kind="run", label="Run demo", action="demo_run", payload={"with_proposal": True}
                ),
            ),
            Step(
                id="model",
                title="Choose a model",
                description="Choose a model and add its provider key. Use Setup for the guided model picker.",
                status="done" if model_ready else "todo",
                cli="uv run paid-media-agent config set PAID_MEDIA_MODEL=anthropic:claude-sonnet-4-6 ANTHROPIC_API_KEY=...",
                action=StepAction(
                    kind="form",
                    label="Save model settings",
                    keys=(
                        "PAID_MEDIA_MODEL",
                        "ANTHROPIC_API_KEY",
                        "OPENAI_API_KEY",
                        "GOOGLE_API_KEY",
                        "PAID_MEDIA_MODEL_BASE_URL",
                        "PAID_MEDIA_TOOL_SELECTOR_MODEL",
                    ),
                ),
                note=str(model.get("selection_reason") or ""),
            ),
            Step(
                id="model_test",
                title="Test the model",
                description="Send one short request to check that your model and API key work.",
                status="optional" if not model_ready else "todo",
                cli="uv run paid-media-agent test model --json",
                action=StepAction(kind="test", label="Test model", action="model_test"),
            ),
            Step(
                id="report",
                title="Run a weekly report",
                description="Compare the last seven complete days with the previous week. Save the report as HTML and PDF.",
                status="optional",
                cli="uv run paid-media-agent report --cadence weekly",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="ask",
                title="Ask a question",
                description="Ask about campaign performance using your configured model and accounts.",
                status="optional",
                cli='uv run paid-media-agent ask "Which campaign moved the most in the last two weeks?"',
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    pipeboard = Route(
        id="pipeboard",
        title="Pipeboard",
        tagline="Ad platforms and Google Analytics",
        description="Connect Google, Meta, TikTok, Pinterest, Snap, Reddit, LinkedIn, and Google Analytics through Pipeboard. Choose the accounts and properties the agent can analyze.",
        steps=(
            Step(
                id="pb_account",
                title="Connect platforms in Pipeboard",
                description="Sign in, connect your ad platforms, and create a scoped read-only API token.",
                status="done" if token_set else "todo",
                cli="open https://pipeboard.co/connections",
                action=StepAction(
                    kind="link", label="Open Pipeboard", href="https://pipeboard.co/connections"
                ),
            ),
            Step(
                id="pb_token",
                title="Add your token",
                description="Add the API token you created in Pipeboard. It is stored locally.",
                status="done" if token_set else "todo",
                cli="uv run paid-media-agent config set PIPEBOARD_API_TOKEN=...",
                action=StepAction(kind="form", label="Save token", keys=("PIPEBOARD_API_TOKEN",)),
            ),
            Step(
                id="pb_test",
                title="Check the connection",
                description="Check which ad platforms and reporting tools your token can access.",
                status="blocked" if not token_set else "todo",
                cli="uv run paid-media-agent test pipeboard --json",
                action=StepAction(kind="test", label="Check connection", action="pipeboard_test"),
            ),
            Step(
                id="pb_accounts",
                title="Choose ad accounts",
                description="Find connected ad accounts and give each a short name to use in conversations.",
                status="done"
                if real_accounts and accounts
                else ("blocked" if not token_set else "todo"),
                cli="uv run paid-media-agent accounts discover --json",
                action=StepAction(
                    kind="accounts", label="Discover accounts", action="accounts_discover"
                ),
            ),
            Step(
                id="pb_live_test",
                title="Test a live account read",
                description="Run the integration test against a connected account. It reads data without changing campaigns.",
                status="optional",
                cli="PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q",
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    org = _get(detail, "org") or {}
    org_configured = bool(isinstance(org, dict) and org.get("configured"))
    org_route = Route(
        id="org",
        title="Business context",
        tagline="Context from your local coding agent",
        description="Your conversion goals, targets, and campaign briefs. Add them with your coding agent before the first real analysis.",
        steps=(
            Step(
                id="org_profile",
                title="Answer in your terminal",
                description="Run from the project folder. Eight short questions cover your business and campaign goals. Enter keeps an existing answer or skips an empty one.",
                status="done" if org_configured else "optional",
                cli="uv run paid-media-agent org interview",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="org_sources",
                title="Add an existing brief",
                description="Use either command with your own public URL or text-file path. Supports Markdown, text, CSV, JSON, and HTML.",
                status="optional",
                cli="uv run paid-media-agent org add-link https://example.com/brief\nuv run paid-media-agent org add-file ./brief.md",
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    direct = Route(
        id="direct",
        title="Direct connections",
        tagline="X and OpenAI Ads",
        description="Connect each platform with its own credentials, then choose the accounts to analyze.",
        steps=(
            Step(
                id="direct_x",
                title="X Ads",
                description="Add the app key and user access tokens from your X developer account. Requires Ads API access.",
                status="done" if direct_set["x"] else "optional",
                cli="uv run paid-media-agent config set X_ADS_CONSUMER_KEY=... X_ADS_CONSUMER_SECRET=... X_ADS_ACCESS_TOKEN=... X_ADS_ACCESS_TOKEN_SECRET=...",
                action=StepAction(
                    kind="form",
                    label="Save X Ads credentials",
                    keys=(
                        "X_ADS_CONSUMER_KEY",
                        "X_ADS_CONSUMER_SECRET",
                        "X_ADS_ACCESS_TOKEN",
                        "X_ADS_ACCESS_TOKEN_SECRET",
                    ),
                ),
            ),
            Step(
                id="direct_openai_ads",
                title="OpenAI Ads",
                description="Add a key issued for the OpenAI Ads API. A model API key does not grant Ads access.",
                status="done" if direct_set["openai_ads"] else "optional",
                cli="uv run paid-media-agent config set OPENAI_ADS_API_KEY=...",
                action=StepAction(
                    kind="form", label="Save OpenAI Ads key", keys=("OPENAI_ADS_API_KEY",)
                ),
            ),
            Step(
                id="direct_accounts",
                title="Choose ad accounts",
                description="Find accounts from your connected platforms and give each a short name.",
                status="done"
                if real_accounts and accounts
                else ("blocked" if not token_set and not any(direct_set.values()) else "todo"),
                cli="uv run paid-media-agent accounts discover --json",
                action=StepAction(
                    kind="accounts", label="Discover accounts", action="accounts_discover"
                ),
            ),
        ),
    )

    sandbox_route = Route(
        id="sandbox",
        title="Sandbox",
        tagline="Tools and files for each conversation",
        description="Included with deployment. MDA builds the Python tools and PDF libraries once, then reuses the snapshot for new conversations.",
        steps=(
            Step(
                id="sb_publish",
                title="Publish a standalone snapshot",
                description="Optional. Build the same recipe separately to test it or reuse it across deployments. No local Docker needed.",
                status="done" if snapshot else "optional",
                cli="uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="sb_test",
                title="Test the environment",
                description="Check a separately published snapshot for Python, file access, and PDF rendering. The temporary test sandbox is removed afterward.",
                status="optional",
                cli="uv run paid-media-agent sandbox test --json",
                action=StepAction(kind="test", label="Test sandbox", action="sandbox_test"),
            ),
        ),
    )

    socket_ready = bool(slack.get("bot_token_set")) and (
        bool(slack.get("app_token_set"))
        if slack.get("transport") == "socket_mode"
        else bool(slack.get("signing_secret_set"))
    )
    slack_route = Route(
        id="slack",
        title="Slack",
        tagline="Connect Slack to a self-hosted agent",
        description="Use your own Slack app with the self-hosted agent. Managed Deep Agents creates its Slack app during deployment.",
        steps=(
            Step(
                id="sl_app",
                title="Create a Slack app",
                description="Use config/slack-manifest.example.yaml, install the app to your workspace, and copy its tokens.",
                status="done" if slack.get("bot_token_set") else "todo",
                cli="open https://api.slack.com/apps?new_app=1",
                action=StepAction(
                    kind="link", label="Open Slack API", href="https://api.slack.com/apps?new_app=1"
                ),
            ),
            Step(
                id="sl_tokens",
                title="Add Slack credentials",
                description="Add a bot token, then an app-level token for Socket Mode or a signing secret for HTTP.",
                status="done" if socket_ready else "todo",
                cli="uv run paid-media-agent config set SLACK_BOT_TOKEN=... SLACK_APP_TOKEN=... SLACK_TRANSPORT=socket_mode",
                action=StepAction(
                    kind="form",
                    label="Save Slack settings",
                    keys=(
                        "SLACK_TRANSPORT",
                        "SLACK_BOT_TOKEN",
                        "SLACK_APP_TOKEN",
                        "SLACK_SIGNING_SECRET",
                    ),
                ),
            ),
            Step(
                id="sl_test",
                title="Test the connection",
                description="Check the bot token and, for Socket Mode, the app-level token.",
                status="blocked" if not socket_ready else "todo",
                cli="uv run paid-media-agent test slack --json",
                action=StepAction(kind="test", label="Test Slack", action="slack_test"),
            ),
            Step(
                id="sl_run",
                title="Start Slack",
                description="Listen for Slack messages on this machine. Connection status and logs appear here.",
                status="blocked" if not socket_ready else "todo",
                cli="uv run paid-media-agent slack",
                action=StepAction(kind="process", label="Start Slack adapter", action="slack"),
            ),
        ),
    )

    mda_ready = (
        bool(mda.get("cli_installed")) and bool(mda.get("langsmith_key_set")) and model_ready
    )
    mda_route = Route(
        id="mda",
        title="Managed Deep Agents",
        tagline="Deploy and manage your hosted agent",
        description="LangSmith hosts your agent, connects Slack, and runs scheduled reports. Use Setup to review settings before deploying.",
        steps=(
            Step(
                id="mda_key",
                title="Add a LangSmith API key",
                description="Use a LangSmith API key with access to your organization.",
                status="done" if mda.get("langsmith_key_set") else "todo",
                cli="uv run paid-media-agent config set LANGSMITH_API_KEY=...",
                action=StepAction(
                    kind="form", label="Save LangSmith key", keys=("LANGSMITH_API_KEY",)
                ),
            ),
            Step(
                id="mda_model",
                title="Model credentials",
                description="Your hosted agent uses this model and its matching provider key.",
                status="done" if model_ready else "todo",
                cli="uv run paid-media-agent config set PAID_MEDIA_MODEL=... ANTHROPIC_API_KEY=...",
                action=StepAction(
                    kind="form",
                    label="Save model settings",
                    keys=(
                        "PAID_MEDIA_MODEL",
                        "ANTHROPIC_API_KEY",
                        "OPENAI_API_KEY",
                        "GOOGLE_API_KEY",
                    ),
                ),
            ),
            Step(
                id="mda_check",
                title="Check deployment setup",
                description="Check the project files, model credentials, and deployment tools before uploading.",
                status="todo" if mda_ready else "blocked",
                cli="uv run paid-media-agent mda check --json",
                action=StepAction(kind="test", label="Check setup", action="mda_check"),
            ),
            Step(
                id="mda_dev",
                title="Run locally in Studio",
                description="Start the agent locally and inspect its conversations and tool calls in Studio.",
                status="optional",
                cli="uv run mda dev",
                action=StepAction(kind="process", label="Start Studio", action="mda-dev"),
            ),
            Step(
                id="mda_deploy",
                title="Deploy your agent",
                description="Review accounts, report schedules, and Slack settings in Setup, then deploy. The first deployment connects Slack.",
                status="blocked" if not mda_ready else "todo",
                cli="uv run mda deploy .",
                action=StepAction(
                    kind="process", label="Deploy", action="mda-deploy", payload={"confirm": True}
                ),
            ),
        ),
    )

    db_set = bool(self_hosted.get("database_url_set"))
    api_set = bool(self_hosted.get("api_tokens_set"))
    self_route = Route(
        id="self_hosted",
        title="Self-host",
        tagline="Run on your own infrastructure",
        description="Run the API and Postgres with Docker, or connect your own database and start the API directly.",
        steps=(
            Step(
                id="sh_docker",
                title="Run with Docker",
                description="Start the API and Postgres together. Model and account credentials come from your local .env file.",
                status="optional",
                cli="docker compose up",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="sh_db",
                title="Connect Postgres",
                description="Connect your own database to save conversations. Docker Compose configures its database automatically.",
                status="done" if db_set else "todo",
                cli="uv run paid-media-agent config set DATABASE_URL=postgresql://...",
                action=StepAction(kind="form", label="Save database URL", keys=("DATABASE_URL",)),
            ),
            Step(
                id="sh_db_test",
                title="Test the database",
                description="Connect to Postgres and check the server version.",
                status="blocked" if not db_set else "todo",
                cli="uv run paid-media-agent test db --json",
                action=StepAction(kind="test", label="Test database", action="database_test"),
            ),
            Step(
                id="sh_tokens",
                title="API credentials",
                description="Create an API access token and a signing key. The token is shown once, so keep it somewhere secure.",
                status="done" if api_set and writes.get("signing_key_set") else "todo",
                cli="uv run paid-media-agent config generate PAID_MEDIA_API_TOKENS && uv run paid-media-agent config generate PAID_MEDIA_APPROVAL_SIGNING_KEY",
                action=StepAction(
                    kind="run", label="Generate credentials", action="generate_secrets"
                ),
            ),
            Step(
                id="sh_serve",
                title="Start the API",
                description="Start the agent API on this machine using the configured host and port.",
                status="todo",
                cli="uv run paid-media-agent serve",
                action=StepAction(kind="process", label="Start API", action="serve"),
            ),
            Step(
                id="sh_http_slack",
                title="Connect Slack over HTTP",
                description="Use an HTTP endpoint instead of Socket Mode. Add the signing secret and configure the request URL in Slack.",
                status="optional",
                cli="uv run paid-media-agent config set SLACK_TRANSPORT=http SLACK_SIGNING_SECRET=...",
                action=StepAction(
                    kind="form",
                    label="Save HTTP transport",
                    keys=("SLACK_TRANSPORT", "SLACK_SIGNING_SECRET"),
                ),
            ),
        ),
    )

    return [
        local,
        pipeboard,
        org_route,
        direct,
        sandbox_route,
        mda_route,
        slack_route,
        self_route,
    ]
