"""Typed settings, model configuration, and host-owned account aliases."""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from paid_media_agent.domain.common import Platform

RuntimeName = Literal["local", "mda", "self_hosted"]
"""Which path the setup console guides you through. Managed Deep Agents is the recommended one."""
SlackTransport = Literal["socket_mode", "http"]

DEFAULT_MODEL_SPEC = "anthropic:claude-sonnet-4-6"


class ModelConfig(BaseModel):
    """Resolved `provider:model` configuration. A gateway is used only via an explicit `langsmith:` spec."""

    model_config = ConfigDict(frozen=True)

    provider: str
    model: str
    base_url: AnyHttpUrl | None = None
    tool_selector_model: str | None = None

    @classmethod
    def parse(
        cls,
        spec: str,
        *,
        base_url: str | None = None,
        tool_selector_model: str | None = None,
    ) -> ModelConfig:
        """Parse `provider:model`. A bare `provider/model` is the older gateway form."""
        raw = spec.strip()
        if raw and ":" not in raw and "/" in raw:
            raw = f"langsmith:{raw}"
        provider, sep, model = raw.partition(":")
        if not sep or not provider.strip() or not model.strip():
            raise ValueError("PAID_MEDIA_MODEL must look like 'provider:model'")
        return cls(
            provider=provider.strip().lower(),
            model=model.strip(),
            base_url=AnyHttpUrl(base_url) if base_url else None,
            tool_selector_model=tool_selector_model or None,
        )

    @property
    def spec(self) -> str:
        return f"{self.provider}:{self.model}"


class AccountBinding(BaseModel):
    """One host-owned mapping from a public alias to a provider account."""

    model_config = ConfigDict(frozen=True)

    alias: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    platform: Platform
    provider_account_id: str = Field(min_length=1)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    timezone: str = Field(min_length=1)


class AccountRegistry(BaseModel):
    """Alias registry. The model only ever sees aliases; provider ids stay host-side."""

    model_config = ConfigDict(frozen=True)

    bindings: tuple[AccountBinding, ...] = ()

    def resolve(self, alias: str) -> AccountBinding | None:
        for binding in self.bindings:
            if binding.alias == alias:
                return binding
        return None

    def aliases(self, platform: Platform | None = None) -> tuple[str, ...]:
        return tuple(b.alias for b in self.bindings if platform is None or b.platform == platform)

    def provider_ids(self) -> frozenset[str]:
        return frozenset(b.provider_account_id for b in self.bindings)

    @classmethod
    def from_toml(cls, path: Path) -> AccountRegistry:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        accounts = data.get("accounts", {})
        if not isinstance(accounts, Mapping):
            raise ValueError("accounts config must contain an [accounts] table")
        bindings = [
            AccountBinding(alias=alias, **values)
            for alias, values in accounts.items()
            if isinstance(values, Mapping)
        ]
        aliases = [b.alias for b in bindings]
        if len(aliases) != len(set(aliases)):
            raise ValueError("duplicate account alias in accounts config")
        return cls(bindings=tuple(bindings))


class Settings(BaseSettings):
    """Process configuration read from the environment. Secrets are never printed."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    paid_media_model: str = DEFAULT_MODEL_SPEC
    paid_media_model_base_url: str | None = None
    paid_media_tool_selector_model: str | None = None
    paid_media_model_api_key_env: str | None = None
    """Env var holding the model API key when the provider does not read its default one."""
    paid_media_model_timeout_seconds: int = Field(default=120, ge=10)
    """Per-request model timeout. A stalled gateway call otherwise blocks a run indefinitely."""
    paid_media_max_model_calls: int = Field(default=40, ge=5)
    """Model calls per run before the agent stops and reports; bounds runaway tool loops."""
    paid_media_runtime: RuntimeName = "local"
    """The deployment path chosen in the console; the command you run selects the runtime."""
    paid_media_sandbox_snapshot: str | None = None
    """Snapshot built from sandbox/Dockerfile and declared to MDA. Empty means the platform image."""
    paid_media_sandbox_idle_ttl_seconds: int = Field(default=1800, ge=60)
    """Idle seconds before MDA deletes a thread's sandbox; written into sandbox/__init__.py."""
    paid_media_log_level: str = "INFO"
    paid_media_workspace_root: Path = Path("workspace")
    paid_media_fixture_anchor: date | None = None
    """Last complete day of the synthetic data. Unset means two days ago, so the demo never ages
    out; tests pin it to the shipped dates. Set it only when reproducing a specific window."""
    paid_media_account_config_path: Path = Path("config/accounts.example.toml")
    paid_media_max_selected_tools: int = Field(default=6, ge=1, le=40)
    paid_media_result_offload_chars: int = Field(default=6000, ge=500)

    pipeboard_api_token: SecretStr | None = None
    pipeboard_google_ads_mcp_url: str = "https://google-ads.mcp.pipeboard.co/"
    pipeboard_meta_ads_mcp_url: str = "https://meta-ads.mcp.pipeboard.co/"
    pipeboard_reddit_ads_mcp_url: str = "https://reddit-ads.mcp.pipeboard.co/"

    # Direct adapters for platforms Pipeboard does not cover. Unset means the platform is absent.
    linkedin_client_id: str | None = None
    linkedin_client_secret: SecretStr | None = None
    linkedin_access_token: SecretStr | None = None
    linkedin_refresh_token: SecretStr | None = None
    x_ads_consumer_key: SecretStr | None = None
    x_ads_consumer_secret: SecretStr | None = None
    x_ads_access_token: SecretStr | None = None
    x_ads_access_token_secret: SecretStr | None = None
    openai_ads_api_key: SecretStr | None = None

    paid_media_writes_enabled: bool = False
    paid_media_write_policy_path: Path = Path("config/write-policy.example.toml")
    paid_media_kill_switch_path: Path = Path("workspace/KILL_SWITCH")
    paid_media_live_write_catalog_revision: str | None = None
    """Catalog revision the operator reviewed for live writes. Live execution requires a match."""
    paid_media_live_write_canary_tools: str = ""
    """Comma-separated qualified mutation names released for the live canary."""
    paid_media_approver_ids: str = ""
    paid_media_approval_signing_key: SecretStr | None = None
    paid_media_approval_ttl_seconds: int = Field(default=900, ge=60, le=86400)
    paid_media_allow_self_approval: bool = False

    # Self-hosted path: the rich Slack adapter, Postgres persistence, and the API boundary.
    slack_bot_token: SecretStr | None = None
    slack_app_token: SecretStr | None = None
    slack_signing_secret: SecretStr | None = None
    slack_transport: SlackTransport = "socket_mode"
    database_url: SecretStr | None = None
    paid_media_api_tokens: SecretStr | None = None
    paid_media_api_host: str = "127.0.0.1"
    paid_media_api_port: int = Field(default=8080, ge=1, le=65535)

    @field_validator(
        "paid_media_model_base_url",
        "paid_media_tool_selector_model",
        "paid_media_model_api_key_env",
        "paid_media_live_write_catalog_revision",
        "linkedin_client_id",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "pipeboard_api_token",
        "linkedin_client_secret",
        "linkedin_access_token",
        "linkedin_refresh_token",
        "x_ads_consumer_key",
        "x_ads_consumer_secret",
        "x_ads_access_token",
        "x_ads_access_token_secret",
        "openai_ads_api_key",
        "paid_media_approval_signing_key",
        "slack_bot_token",
        "slack_app_token",
        "slack_signing_secret",
        "database_url",
        "paid_media_api_tokens",
        mode="before",
    )
    @classmethod
    def _blank_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def model_settings(self) -> ModelConfig:
        return ModelConfig.parse(
            self.paid_media_model,
            base_url=self.paid_media_model_base_url,
            tool_selector_model=self.paid_media_tool_selector_model,
        )

    def live_write_canary_tools(self) -> frozenset[str]:
        return frozenset(
            part.strip()
            for part in self.paid_media_live_write_canary_tools.split(",")
            if part.strip()
        )

    def approver_refs(self) -> frozenset[str]:
        return frozenset(
            part.strip() for part in self.paid_media_approver_ids.split(",") if part.strip()
        )

    def pipeboard_endpoints(self) -> dict[Platform, str]:
        return {
            Platform.GOOGLE_ADS: self.pipeboard_google_ads_mcp_url,
            Platform.META_ADS: self.pipeboard_meta_ads_mcp_url,
            Platform.REDDIT_ADS: self.pipeboard_reddit_ads_mcp_url,
        }

    def direct_platforms(self) -> tuple[Platform, ...]:
        """Direct-adapter platforms with complete credentials."""
        platforms: list[Platform] = []
        if self.linkedin_access_token is not None:
            platforms.append(Platform.LINKEDIN_ADS)
        if None not in (
            self.x_ads_consumer_key,
            self.x_ads_consumer_secret,
            self.x_ads_access_token,
            self.x_ads_access_token_secret,
        ):
            platforms.append(Platform.X_ADS)
        if self.openai_ads_api_key is not None:
            platforms.append(Platform.OPENAI_ADS)
        return tuple(platforms)

    def api_token_map(self) -> dict[str, str]:
        """Parse `token:caller_ref,token:caller_ref` into a lookup. Values stay in memory only."""
        if self.paid_media_api_tokens is None:
            return {}
        result: dict[str, str] = {}
        for pair in self.paid_media_api_tokens.get_secret_value().split(","):
            token, sep, caller = pair.strip().partition(":")
            if sep and token and caller:
                result[token] = caller
        return result


def project_root(start: Path | None = None) -> Path:
    """The repository root: the nearest ancestor holding `instructions.md` and `skills/`."""
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "instructions.md").exists() and (candidate / "skills").is_dir():
            return candidate
    return Path.cwd()
