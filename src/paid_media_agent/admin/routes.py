"""Onboarding routes: ordered steps whose status is derived from the current host state."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.domain.common import JsonValue

StepStatus = Literal["done", "todo", "optional", "blocked"]
ActionKind = Literal[
    "form", "test", "run", "process", "link", "command", "accounts", "policy", "kill_switch"
]


class StepAction(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: ActionKind
    label: str
    keys: tuple[str, ...] = ()
    """Env keys a `form` action edits."""
    action: str = ""
    """Server action name for `test`, `run`, `process`, `accounts`, `policy`, `kill_switch`."""
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
        "linkedin": ("LINKEDIN_ACCESS_TOKEN",),
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
    sandbox_backend = (
        isinstance(env, dict) and str(env.get("PAID_MEDIA_BACKEND") or "local") == "sandbox"
    )

    local = Route(
        id="local",
        title="Local demo",
        tagline="Prove the install, then pick a model",
        description="Run the fixture demo with no credentials, then configure a real model for live questions.",
        steps=(
            Step(
                id="tooling",
                title="Toolchain",
                description="Python 3.11+, uv, and the locked dependencies.",
                status="done" if _get(detail, "tooling", "uv") else "todo",
                cli="uv sync --all-extras --dev",
            ),
            Step(
                id="demo",
                title="Run the fixture demo",
                description="A scripted model drives the real graph against synthetic accounts and returns a reconciled comparison.",
                status="todo",
                cli="uv run paid-media-agent demo --with-proposal",
                action=StepAction(
                    kind="run", label="Run demo", action="demo_run", payload={"with_proposal": True}
                ),
            ),
            Step(
                id="model",
                title="Choose a model",
                description="Set PAID_MEDIA_MODEL as provider:model and the matching key. Registered Anthropic and OpenAI models get provider-native tool search.",
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
                description="One short call proves the key, the package, and the selection path.",
                status="optional" if not model_ready else "todo",
                cli="uv run paid-media-agent test model --json",
                action=StepAction(kind="test", label="Test model", action="model_test"),
            ),
            Step(
                id="report",
                title="Run the weekly report",
                description="Reads every alias, compares the last 7 complete days with the 7 before, renders HTML and PDF. No model involved.",
                status="optional",
                cli="uv run paid-media-agent report --cadence weekly",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="ask",
                title="Ask a question",
                description="Run one real question through the shared assembly against the fixture accounts.",
                status="optional",
                cli='uv run python examples/ask.py "Which fixture campaign moved the most in the last two weeks?"',
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    pipeboard = Route(
        id="pipeboard",
        title="Connect Pipeboard",
        tagline="Real ad accounts through one scoped token",
        description="Pipeboard owns the platform OAuth. Connect Google, Meta, and Reddit there, create a scoped token, and map aliases here.",
        steps=(
            Step(
                id="pb_account",
                title="Connect platforms in Pipeboard",
                description="Sign in, connect each ad platform, and create a scoped read-only API token.",
                status="done" if token_set else "todo",
                cli="open https://pipeboard.co/api-tokens",
                action=StepAction(
                    kind="link", label="Open Pipeboard", href="https://pipeboard.co/api-tokens"
                ),
            ),
            Step(
                id="pb_token",
                title="Store the token",
                description="The token stays in .env and is sent only as a bearer header to Pipeboard's MCP endpoints.",
                status="done" if token_set else "todo",
                cli="uv run paid-media-agent config set PIPEBOARD_API_TOKEN=...",
                action=StepAction(kind="form", label="Save token", keys=("PIPEBOARD_API_TOKEN",)),
            ),
            Step(
                id="pb_test",
                title="Load the live catalog",
                description="Counts read, admitted, and denied tools per platform and prints the catalog revision.",
                status="blocked" if not token_set else "todo",
                cli="uv run paid-media-agent test pipeboard --json",
                action=StepAction(kind="test", label="Load catalog", action="pipeboard_test"),
            ),
            Step(
                id="pb_accounts",
                title="Discover and map accounts",
                description="Host-side account listing; pick an alias per account. The model only ever sees aliases.",
                status="done"
                if real_accounts and accounts
                else ("blocked" if not token_set else "todo"),
                cli="uv run paid-media-agent accounts discover --json",
                action=StepAction(
                    kind="accounts", label="Discover accounts", action="accounts_discover"
                ),
            ),
            Step(
                id="pb_policy",
                title="Validate the write policy against the live catalog",
                description="Rows that the live schema cannot honor are excluded and listed here.",
                status="blocked" if not token_set else "todo",
                cli="uv run paid-media-agent policy validate --live --json",
                action=StepAction(
                    kind="policy",
                    label="Validate policy",
                    action="policy_validate",
                    payload={"live": True},
                ),
            ),
            Step(
                id="pb_live_test",
                title="Run the read-only live check",
                description="Opt-in integration test that loads the catalog and performs one read.",
                status="optional",
                cli="PAID_MEDIA_LIVE_TESTS=1 uv run pytest tests/integration -q",
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    socket_ready = bool(slack.get("bot_token_set")) and (
        bool(slack.get("app_token_set"))
        if slack.get("transport") == "socket_mode"
        else bool(slack.get("signing_secret_set"))
    )
    org = _get(detail, "org") or {}
    org_configured = bool(isinstance(org, dict) and org.get("configured"))
    org_route = Route(
        id="org",
        title="Your business",
        tagline="Goals, conversions, targets, naming, approvers, and the docs you share",
        description="Eight plain questions the agent reads before every analysis, plus links and files. Stored in docs/org, never committed.",
        steps=(
            Step(
                id="org_profile",
                title="Answer the interview",
                description="What you sell, the conversion that counts, targets or directional, budget, markets, seasonality, naming, approvers.",
                status="done" if org_configured else "todo",
                cli="uv run paid-media-agent org interview",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="org_sources",
                title="Share briefs and exports",
                description="Public links are fetched as text; text files are copied. Both are listed on /docs/org/sources.md.",
                status="optional",
                cli="uv run paid-media-agent org add-link https://... ; uv run paid-media-agent org add-file ./brief.md",
                action=StepAction(kind="command", label="Copy command"),
            ),
        ),
    )

    direct = Route(
        id="direct",
        title="Direct platforms",
        tagline="LinkedIn Ads, X Ads, and OpenAI Ads without Pipeboard",
        description="These platforms are not on Pipeboard. Paste platform credentials; the adapters join the same authorized catalog with read-only tools.",
        steps=(
            Step(
                id="direct_linkedin",
                title="LinkedIn Ads",
                description="OAuth 2.0 access token; add the refresh token, client id, and secret so the adapter can refresh once on 401.",
                status="done" if direct_set["linkedin"] else "optional",
                cli="uv run paid-media-agent config set LINKEDIN_ACCESS_TOKEN=... LINKEDIN_REFRESH_TOKEN=... LINKEDIN_CLIENT_ID=... LINKEDIN_CLIENT_SECRET=...",
                action=StepAction(
                    kind="form",
                    label="Save LinkedIn credentials",
                    keys=(
                        "LINKEDIN_ACCESS_TOKEN",
                        "LINKEDIN_REFRESH_TOKEN",
                        "LINKEDIN_CLIENT_ID",
                        "LINKEDIN_CLIENT_SECRET",
                    ),
                ),
            ),
            Step(
                id="direct_x",
                title="X Ads",
                description="OAuth 1.0a app credentials and user tokens from the X developer portal; requests are signed locally.",
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
                description="Bearer API key for the OpenAI Ads API.",
                status="done" if direct_set["openai_ads"] else "optional",
                cli="uv run paid-media-agent config set OPENAI_ADS_API_KEY=...",
                action=StepAction(
                    kind="form", label="Save OpenAI Ads key", keys=("OPENAI_ADS_API_KEY",)
                ),
            ),
            Step(
                id="direct_accounts",
                title="Discover and map accounts",
                description="Lists accounts from every configured direct platform next to Pipeboard ones; pick an alias per account.",
                status="done"
                if real_accounts and accounts
                else ("blocked" if not any(direct_set.values()) else "todo"),
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
        tagline="The model's files in a LangSmith sandbox, locally and in production",
        description="Build the image from sandbox/Dockerfile on LangSmith (no local Docker), point every runtime at it, and prove it can host the agent before you deploy.",
        steps=(
            Step(
                id="sb_publish",
                title="Publish the snapshot",
                description="LangSmith builds sandbox/Dockerfile and the result is declared for our runtimes and for MDA.",
                status="done" if snapshot else "todo",
                cli="uv run paid-media-agent sandbox publish --name paid-media-agent-sandbox",
                action=StepAction(kind="command", label="Copy command"),
            ),
            Step(
                id="sb_backend",
                title="Run against the sandbox",
                description="langgraph dev, serve, and the console then mount skills and the wiki in the sandbox, mirror artifacts, and render PDFs inside it.",
                status="done" if sandbox_backend else "optional",
                cli="uv run paid-media-agent config set PAID_MEDIA_BACKEND=sandbox",
                action=StepAction(
                    kind="form",
                    label="Save",
                    keys=("PAID_MEDIA_BACKEND", "PAID_MEDIA_SANDBOX_SNAPSHOT"),
                ),
            ),
            Step(
                id="sb_test",
                title="Probe the sandbox",
                description="Opens one sandbox, checks Python, mounts, the workspace, an in-sandbox PDF, and secret hygiene, then deletes it.",
                status="blocked" if not _get(detail, "mda", "langsmith_key_set") else "todo",
                cli="uv run paid-media-agent sandbox test --json",
                action=StepAction(kind="test", label="Probe sandbox", action="sandbox_test"),
            ),
        ),
    )

    slack_route = Route(
        id="slack",
        title="Slack (rich adapter)",
        tagline="Block Kit review cards, edits, receipts, and files",
        description="Socket Mode needs no public URL. Signed HTTP is the hosted alternative. Both use the same application service.",
        steps=(
            Step(
                id="sl_app",
                title="Create the Slack app from the manifest",
                description="Use config/slack-manifest.example.yaml, install it to your workspace, and copy the tokens.",
                status="done" if slack.get("bot_token_set") else "todo",
                cli="open https://api.slack.com/apps?new_app=1",
                action=StepAction(
                    kind="link", label="Open Slack API", href="https://api.slack.com/apps?new_app=1"
                ),
            ),
            Step(
                id="sl_tokens",
                title="Store the tokens",
                description="Bot token, and either the app-level token (Socket Mode) or the signing secret (HTTP).",
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
                description="auth.test with the bot token and a Socket Mode ticket with the app token.",
                status="blocked" if not socket_ready else "todo",
                cli="uv run paid-media-agent test slack --json",
                action=StepAction(kind="test", label="Test Slack", action="slack_test"),
            ),
            Step(
                id="sl_approvers",
                title="Name the approvers",
                description="Refs look like slack:<team_id>:<user_id>. Card location is never authorization.",
                status="done" if writes.get("approvers") else "todo",
                cli="uv run paid-media-agent config set PAID_MEDIA_APPROVER_IDS=slack:T123:U456",
                action=StepAction(
                    kind="form",
                    label="Save approvers",
                    keys=("PAID_MEDIA_APPROVER_IDS", "PAID_MEDIA_ALLOW_SELF_APPROVAL"),
                ),
            ),
            Step(
                id="sl_run",
                title="Run the adapter",
                description="Starts Socket Mode locally and keeps the log here.",
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
        title="Deploy to MDA",
        tagline="Managed threads, sandbox, schedules, and native Slack",
        description="agent.py, instructions.md, skills/, and channels/slack.py are the managed project files. Secrets travel from .env at deploy time.",
        steps=(
            Step(
                id="mda_key",
                title="Add a LangSmith API key",
                description="Used only to authenticate mda dev and mda deploy, never for model access.",
                status="done" if mda.get("langsmith_key_set") else "todo",
                cli="uv run paid-media-agent config set LANGSMITH_API_KEY=...",
                action=StepAction(
                    kind="form", label="Save LangSmith key", keys=("LANGSMITH_API_KEY",)
                ),
            ),
            Step(
                id="mda_model",
                title="Model and provider key",
                description="The managed runtime uses the same PAID_MEDIA_MODEL and provider key.",
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
                title="Preflight",
                description="CLI present, agent.py imports, channels/slack.py declared, provider key available.",
                status="todo" if mda_ready else "blocked",
                cli="uv run paid-media-agent mda check --json",
                action=StepAction(kind="test", label="Run preflight", action="mda_check"),
            ),
            Step(
                id="mda_dev",
                title="Run locally with LangSmith Studio",
                description="mda dev runs the managed runtime locally against your .env.",
                status="optional",
                cli="uv run mda dev",
                action=StepAction(kind="process", label="Start mda dev", action="mda-dev"),
            ),
            Step(
                id="mda_deploy",
                title="Deploy",
                description="Builds and deploys to LangSmith Cloud (US). The first deploy prints a Slack authorization link in the log.",
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
        tagline="Postgres, your API, your Slack app, your infrastructure",
        description="The same assembly compiled with create_deep_agent, durable state in Postgres, and a small authenticated FastAPI boundary.",
        steps=(
            Step(
                id="sh_db",
                title="Postgres",
                description="DATABASE_URL for checkpoints, proposals, approvals, receipts, and dedupe.",
                status="done" if db_set else "todo",
                cli="uv run paid-media-agent config set DATABASE_URL=postgresql://...",
                action=StepAction(kind="form", label="Save database URL", keys=("DATABASE_URL",)),
            ),
            Step(
                id="sh_db_test",
                title="Test the database",
                description="Connects and reads the server version.",
                status="blocked" if not db_set else "todo",
                cli="uv run paid-media-agent test db --json",
                action=StepAction(kind="test", label="Test database", action="database_test"),
            ),
            Step(
                id="sh_tokens",
                title="API tokens and signing key",
                description="Generate a caller token for the API and the HMAC key that signs approvals.",
                status="done" if api_set and writes.get("signing_key_set") else "todo",
                cli="uv run paid-media-agent config generate PAID_MEDIA_API_TOKENS && uv run paid-media-agent config generate PAID_MEDIA_APPROVAL_SIGNING_KEY",
                action=StepAction(kind="run", label="Generate secrets", action="generate_secrets"),
            ),
            Step(
                id="sh_approvers",
                title="Approvers",
                description="API caller names or Slack refs that may approve, edit, or reject.",
                status="done" if writes.get("approvers") else "todo",
                cli="uv run paid-media-agent config set PAID_MEDIA_APPROVER_IDS=operator",
                action=StepAction(
                    kind="form",
                    label="Save approvers",
                    keys=("PAID_MEDIA_APPROVER_IDS", "PAID_MEDIA_ALLOW_SELF_APPROVAL"),
                ),
            ),
            Step(
                id="sh_serve",
                title="Run the API",
                description="Serves threads, proposals, approvals, artifacts, and health on the configured host and port.",
                status="todo",
                cli="uv run paid-media-agent serve",
                action=StepAction(kind="process", label="Start API", action="serve"),
            ),
            Step(
                id="sh_http_slack",
                title="Slack over signed HTTP",
                description="For a hosted deployment, set the signing secret and point the Slack request URL at your public endpoint.",
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

    writes_route = Route(
        id="writes",
        title="Write gates",
        tagline="Proposals always; live mutations only behind every gate",
        description="Automated tests can never reach a live mutation. The gates below are the only way an operator releases one, and the kill switch stops everything.",
        steps=(
            Step(
                id="w_policy",
                title="Reviewed mutation set",
                description="Rows in the write-policy file validated against the catalog. Removing a row is the rollback.",
                status="done"
                if int(str(writes.get("policy_operations") or 0)) > 0
                and not writes.get("policy_issues")
                else "todo",
                cli="uv run paid-media-agent policy validate --json",
                action=StepAction(kind="policy", label="Validate policy", action="policy_validate"),
            ),
            Step(
                id="w_kill",
                title="Kill switch",
                description="Engaging it refuses every execution, including fakes, until the file is removed.",
                status="done" if not writes.get("kill_switch_engaged") else "todo",
                cli="uv run paid-media-agent writes kill-switch on",
                action=StepAction(
                    kind="kill_switch", label="Toggle kill switch", action="kill_switch"
                ),
                note="engaged" if writes.get("kill_switch_engaged") else "clear",
            ),
            Step(
                id="w_release",
                title="Release a live canary",
                description="Requires the global flag, the pinned reviewed catalog revision, and a single canary tool. Read the runbook first.",
                status="optional",
                cli="uv run paid-media-agent config set PAID_MEDIA_WRITES_ENABLED=true PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION=<rev> PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS=<tool>",
                action=StepAction(
                    kind="form",
                    label="Edit gate settings",
                    keys=(
                        "PAID_MEDIA_WRITES_ENABLED",
                        "PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION",
                        "PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS",
                    ),
                ),
                note="docs/operations/live-write-runbook.md",
            ),
        ),
    )
    return [
        local,
        pipeboard,
        org_route,
        direct,
        sandbox_route,
        slack_route,
        mda_route,
        self_route,
        writes_route,
    ]
