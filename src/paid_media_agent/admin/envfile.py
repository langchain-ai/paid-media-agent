"""Read and write the local `.env` safely: allowlisted keys, masked values, 0600 file."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_LINE_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*(.*)$")


class EnvKeySpec(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    group: str
    secret: bool
    description: str
    example: str = ""


ENV_KEYS: tuple[EnvKeySpec, ...] = (
    EnvKeySpec(
        name="PAID_MEDIA_MODEL",
        group="model",
        secret=False,
        description="provider:model, e.g. anthropic:claude-sonnet-4-6",
        example="anthropic:claude-sonnet-4-6",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_MODEL_BASE_URL",
        group="model",
        secret=False,
        description="Optional compatible base URL; disables provider-native tool search",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_TOOL_SELECTOR_MODEL",
        group="model",
        secret=False,
        description="Cheaper model for the portable tool selector",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_MODEL_API_KEY_ENV",
        group="model",
        secret=False,
        description="Env var that holds the model key, for providers without a default",
    ),
    EnvKeySpec(name="GROQ_API_KEY", group="model", secret=True, description="Groq API key"),
    EnvKeySpec(name="XAI_API_KEY", group="model", secret=True, description="xAI API key"),
    EnvKeySpec(name="MISTRAL_API_KEY", group="model", secret=True, description="Mistral API key"),
    EnvKeySpec(name="DEEPSEEK_API_KEY", group="model", secret=True, description="DeepSeek API key"),
    EnvKeySpec(name="OPENROUTER_API_KEY", group="model", secret=True, description="OpenRouter key"),
    EnvKeySpec(
        name="MOONSHOT_API_KEY", group="model", secret=True, description="Moonshot (Kimi) key"
    ),
    EnvKeySpec(name="ZHIPU_API_KEY", group="model", secret=True, description="Zhipu (GLM) key"),
    EnvKeySpec(
        name="ANTHROPIC_API_KEY", group="model", secret=True, description="Anthropic API key"
    ),
    EnvKeySpec(name="OPENAI_API_KEY", group="model", secret=True, description="OpenAI API key"),
    EnvKeySpec(
        name="GOOGLE_API_KEY", group="model", secret=True, description="Google Generative AI key"
    ),
    EnvKeySpec(
        name="PAID_MEDIA_RUNTIME",
        group="runtime",
        secret=False,
        description="local, mda, or self_hosted",
        example="local",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_LOG_LEVEL",
        group="runtime",
        secret=False,
        description="Log level",
        example="INFO",
    ),
    EnvKeySpec(
        name="PIPEBOARD_API_TOKEN",
        group="pipeboard",
        secret=True,
        description="Scoped Pipeboard API token",
    ),
    EnvKeySpec(
        name="PIPEBOARD_GOOGLE_ADS_MCP_URL",
        group="pipeboard",
        secret=False,
        description="Google Ads MCP endpoint",
    ),
    EnvKeySpec(
        name="PIPEBOARD_META_ADS_MCP_URL",
        group="pipeboard",
        secret=False,
        description="Meta Ads MCP endpoint",
    ),
    EnvKeySpec(
        name="PIPEBOARD_REDDIT_ADS_MCP_URL",
        group="pipeboard",
        secret=False,
        description="Reddit Ads MCP endpoint",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_ACCOUNT_CONFIG_PATH",
        group="pipeboard",
        secret=False,
        description="Account alias TOML path",
        example="config/accounts.toml",
    ),
    EnvKeySpec(
        name="LINKEDIN_CLIENT_ID",
        group="direct",
        secret=False,
        description="LinkedIn app client id (token refresh)",
    ),
    EnvKeySpec(
        name="LINKEDIN_CLIENT_SECRET",
        group="direct",
        secret=True,
        description="LinkedIn app client secret (token refresh)",
    ),
    EnvKeySpec(
        name="LINKEDIN_ACCESS_TOKEN",
        group="direct",
        secret=True,
        description="LinkedIn Marketing API access token",
    ),
    EnvKeySpec(
        name="LINKEDIN_REFRESH_TOKEN",
        group="direct",
        secret=True,
        description="LinkedIn refresh token",
    ),
    EnvKeySpec(
        name="X_ADS_CONSUMER_KEY", group="direct", secret=True, description="X Ads API consumer key"
    ),
    EnvKeySpec(
        name="X_ADS_CONSUMER_SECRET",
        group="direct",
        secret=True,
        description="X Ads API consumer secret",
    ),
    EnvKeySpec(
        name="X_ADS_ACCESS_TOKEN", group="direct", secret=True, description="X Ads API access token"
    ),
    EnvKeySpec(
        name="X_ADS_ACCESS_TOKEN_SECRET",
        group="direct",
        secret=True,
        description="X Ads API access token secret",
    ),
    EnvKeySpec(
        name="OPENAI_ADS_API_KEY", group="direct", secret=True, description="OpenAI Ads API key"
    ),
    EnvKeySpec(
        name="PAID_MEDIA_WRITES_ENABLED",
        group="writes",
        secret=False,
        description="Global write flag; live writes still need the release gates",
        example="false",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_APPROVER_IDS",
        group="writes",
        secret=False,
        description="Comma-separated approver refs (slack:<team>:<user> or API caller names)",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_APPROVAL_SIGNING_KEY",
        group="writes",
        secret=True,
        description="HMAC key for approval claims",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_APPROVAL_TTL_SECONDS",
        group="writes",
        secret=False,
        description="Approval validity window",
        example="900",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_ALLOW_SELF_APPROVAL",
        group="writes",
        secret=False,
        description="Let a requester approve their own proposal",
        example="false",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_WRITE_POLICY_PATH",
        group="writes",
        secret=False,
        description="Reviewed mutation set TOML",
        example="config/write-policy.example.toml",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_KILL_SWITCH_PATH",
        group="writes",
        secret=False,
        description="Kill-switch file path",
        example="workspace/KILL_SWITCH",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_LIVE_WRITE_CATALOG_REVISION",
        group="writes",
        secret=False,
        description="Reviewed catalog revision pinned for the live canary",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_LIVE_WRITE_CANARY_TOOLS",
        group="writes",
        secret=False,
        description="Comma-separated mutation names released for the canary",
    ),
    EnvKeySpec(name="SLACK_BOT_TOKEN", group="slack", secret=True, description="Bot token (xoxb-)"),
    EnvKeySpec(
        name="SLACK_APP_TOKEN",
        group="slack",
        secret=True,
        description="App-level token for Socket Mode (xapp-)",
    ),
    EnvKeySpec(
        name="SLACK_SIGNING_SECRET",
        group="slack",
        secret=True,
        description="Signing secret for the HTTP transport",
    ),
    EnvKeySpec(
        name="SLACK_TRANSPORT",
        group="slack",
        secret=False,
        description="socket_mode or http",
        example="socket_mode",
    ),
    EnvKeySpec(
        name="DATABASE_URL",
        group="self_hosted",
        secret=True,
        description="Postgres connection string",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_API_TOKENS",
        group="self_hosted",
        secret=True,
        description="token:caller pairs for the API",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_API_HOST",
        group="self_hosted",
        secret=False,
        description="API bind host",
        example="127.0.0.1",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_API_PORT",
        group="self_hosted",
        secret=False,
        description="API port",
        example="8080",
    ),
    EnvKeySpec(
        name="LANGSMITH_API_KEY",
        group="mda",
        secret=True,
        description="LangSmith key for mda dev, mda deploy, and the LLM Gateway",
    ),
    EnvKeySpec(
        name="LANGSMITH_GATEWAY_API_KEY",
        group="model",
        secret=True,
        description="Second LangSmith key for the gateway; point PAID_MEDIA_MODEL_API_KEY_ENV at it",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_MODEL_TIMEOUT_SECONDS",
        group="model",
        secret=False,
        description="Per-request model timeout in seconds",
        example="120",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_MAX_MODEL_CALLS",
        group="model",
        secret=False,
        description="Model calls per run before the agent stops",
        example="40",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_WORKSPACE_ROOT",
        group="runtime",
        secret=False,
        description="Workspace directory for artifacts and reports",
        example="workspace",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_MAX_SELECTED_TOOLS",
        group="model",
        secret=False,
        description="Platform tools the selector may bind per turn",
        example="6",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_RESULT_OFFLOAD_CHARS",
        group="model",
        secret=False,
        description="Tool results longer than this become workspace artifacts",
        example="6000",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_SANDBOX_IDLE_TTL_SECONDS",
        group="sandbox",
        secret=False,
        description="Idle seconds before a sandbox stops",
        example="1800",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_BACKEND",
        group="sandbox",
        secret=False,
        description="Where the model's files live: local (repository) or sandbox (LangSmith)",
        example="local",
    ),
    EnvKeySpec(
        name="PAID_MEDIA_SANDBOX_SNAPSHOT",
        group="sandbox",
        secret=False,
        description="Snapshot name built from sandbox/Dockerfile",
        example="paid-media-agent-sandbox",
    ),
)
ENV_KEY_BY_NAME: dict[str, EnvKeySpec] = {spec.name: spec for spec in ENV_KEYS}
_CUSTOM_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,40}_API_KEY$")
"""Any provider key name is allowed as long as it looks like one; it is always a secret."""


def key_spec(name: str) -> EnvKeySpec | None:
    spec = ENV_KEY_BY_NAME.get(name)
    if spec is not None:
        return spec
    if _CUSTOM_KEY_RE.match(name):
        return EnvKeySpec(name=name, group="model", secret=True, description="Provider API key")
    return None


class EnvKeyView(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    group: str
    secret: bool
    description: str
    example: str
    is_set: bool
    value: str
    """Plain value for non-secrets; a fixed mask for secrets; empty when unset."""


class EnvFileError(ValueError):
    pass


def env_path(root: Path) -> Path:
    return root / ".env"


def _unquote(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        inner = value[1:-1]
        return inner.replace('\\"', '"').replace("\\\\", "\\") if value[0] == '"' else inner
    hash_index = value.find(" #")
    return value[:hash_index].rstrip() if hash_index >= 0 else value


def _quote(value: str) -> str:
    if value == "" or any(ch in value for ch in (" ", "#", '"', "'", "=")):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def read_env(root: Path) -> dict[str, str]:
    path = env_path(root)
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _LINE_RE.match(line)
        if match and not line.lstrip().startswith("#"):
            values[match.group(1)] = _unquote(match.group(2))
    return values


def masked_env(root: Path) -> list[EnvKeyView]:
    values = read_env(root)
    views: list[EnvKeyView] = []
    custom = [key_spec(name) for name in values if name not in ENV_KEY_BY_NAME]
    for spec in (*ENV_KEYS, *(c for c in custom if c is not None)):
        raw = values.get(spec.name, "")
        is_set = bool(raw.strip())
        shown = "" if not is_set else ("••••••••" if spec.secret else raw)
        views.append(
            EnvKeyView(
                name=spec.name,
                group=spec.group,
                secret=spec.secret,
                description=spec.description,
                example=spec.example,
                is_set=is_set,
                value=shown,
            )
        )
    return views


def _validate(updates: Mapping[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for key, value in updates.items():
        if key_spec(key) is None:
            raise EnvFileError(f"{key} is not a configurable key")
        if not isinstance(value, str) or "\n" in value or "\r" in value or "\x00" in value:
            raise EnvFileError(f"{key} value must be a single line")
        clean[key] = value.strip()
    return clean


def write_env(root: Path, updates: Mapping[str, str]) -> list[str]:
    """Set keys in `.env`, preserving unrelated lines and comments. Returns the keys written."""
    clean = _validate(updates)
    path = env_path(root)
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    else:
        example = root / ".env.example"
        lines = example.read_text(encoding="utf-8").splitlines() if example.exists() else []
    remaining = dict(clean)
    output: list[str] = []
    for line in lines:
        match = _LINE_RE.match(line)
        key = match.group(1) if match and not line.lstrip().startswith("#") else None
        if key is not None and key in remaining:
            output.append(f"{key}={_quote(remaining.pop(key))}")
        else:
            output.append(line)
    for key, value in remaining.items():
        output.append(f"{key}={_quote(value)}")
    text = "\n".join(output).rstrip("\n") + "\n"
    existed = path.exists()
    path.write_text(text, encoding="utf-8")
    if not existed or (path.stat().st_mode & 0o077):
        os.chmod(path, 0o600)
    return list(clean)


_EXPORTED_BY_CONSOLE: set[str] = set()


def apply_env_file(root: Path) -> list[str]:
    """Export allowlisted `.env` values into this process so provider SDKs and child processes see them.

    The console exists to manage `.env`, so the file wins over stale process values. Only known
    keys are exported. A key the console exported earlier and that is now blank in the file is
    removed again, so clearing a base URL or key in the page takes effect; values the operator set
    in their own shell are never touched.
    """
    exported: list[str] = []
    values = read_env(root)
    for key, value in values.items():
        if key_spec(key) is None:
            continue
        if value.strip():
            os.environ[key] = value
            _EXPORTED_BY_CONSOLE.add(key)
            exported.append(key)
        elif key in _EXPORTED_BY_CONSOLE:
            os.environ.pop(key, None)
            _EXPORTED_BY_CONSOLE.discard(key)
    return exported
