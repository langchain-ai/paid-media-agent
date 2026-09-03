"""Host actions shared by the CLI and the local console. Every action returns a typed result."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import re
import secrets
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from paid_media_agent.admin.accounts_file import (
    AccountsFileError,
    active_accounts_path,
    add_account,
    read_accounts,
    remove_account,
    writable_accounts_path,
)
from paid_media_agent.admin.envfile import (
    EnvFileError,
    apply_env_file,
    masked_env,
    read_env,
    write_env,
)
from paid_media_agent.config import AccountBinding, Settings
from paid_media_agent.doctor import Check, run_doctor, run_snapshot_checks
from paid_media_agent.domain.common import PIPEBOARD_PLATFORMS, JsonValue, Platform
from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.middleware.tool_selection import capabilities_for, plan_selection
from paid_media_agent.runtime.profiles import load_write_policy_file
from paid_media_agent.tools.catalog import AuthorizedToolCatalog
from paid_media_agent.tools.fixtures import build_fixture_catalog, load_fixture_dataset

Status = Literal["ok", "warn", "fail", "skipped"]


class ActionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str
    ok: bool
    status: Status
    summary: str
    detail: dict[str, JsonValue] = Field(default_factory=dict)
    command: str = ""
    """Equivalent CLI invocation, so agents and humans share one path."""


def _result(
    action: str,
    status: Status,
    summary: str,
    detail: dict[str, JsonValue] | None = None,
    command: str = "",
) -> ActionResult:
    return ActionResult(
        action=action,
        ok=status in ("ok", "skipped"),
        status=status,
        summary=summary,
        detail=detail or {},
        command=command,
    )


def _checks_json(checks: list[Check]) -> list[dict[str, JsonValue]]:
    return [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks]


def load_settings(root: Path) -> Settings:
    """Settings from the project `.env`, exported into the process so SDKs and children see them."""
    apply_env_file(root)
    return Settings(_env_file=str(root / ".env"))


# ---------------------------------------------------------------- status and configuration


def catalog_summary(catalog: AuthorizedToolCatalog) -> dict[str, JsonValue]:
    per_platform: dict[str, dict[str, int]] = {}
    for entry in catalog.entries:
        bucket = per_platform.setdefault(
            entry.platform.value, {"read": 0, "mutation": 0, "denied": 0}
        )
        bucket[entry.tool_class.value] += 1
    return {
        "source": catalog.source,
        "revision": catalog.revision,
        "read": len(catalog.read_entries()),
        "mutation": len(catalog.mutation_entries()),
        "denied": len(catalog.denied_entries()),
        "platforms": per_platform,
        "denied_reasons": sorted({e.policy.reason for e in catalog.denied_entries()}),
    }


MODEL_PRESETS: tuple[dict[str, JsonValue], ...] = (
    {
        "id": "langsmith",
        "label": "LangSmith Gateway",
        "model": "anthropic/claude-sonnet-4-6",
        "key": "LANGSMITH_API_KEY",
        "url": "https://smith.langchain.com/settings",
        "note": "One key, every provider, traced",
        "package": "",
        "recommended": True,
        "logo": "langchain",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "logo": "anthropic",
        "model": "anthropic:claude-sonnet-4-6",
        "key": "ANTHROPIC_API_KEY",
        "package": "",
        "extra": "anthropic",
        "url": "https://console.anthropic.com/settings/keys",
        "note": "Native tool search",
        "recommended": False,
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "logo": "openai",
        "model": "openai:gpt-5.5",
        "key": "OPENAI_API_KEY",
        "package": "",
        "extra": "openai",
        "url": "https://platform.openai.com/api-keys",
        "note": "Native tool search",
    },
    {
        "id": "google",
        "label": "Google",
        "logo": "gemini",
        "model": "google_genai:gemini-3-flash",
        "key": "GOOGLE_API_KEY",
        "package": "langchain_google_genai",
        "extra": "google",
        "url": "https://aistudio.google.com/app/apikey",
        "note": "Portable selector",
    },
    {
        "id": "groq",
        "label": "Groq",
        "logo": "groq",
        "model": "groq:llama-3.3-70b-versatile",
        "key": "GROQ_API_KEY",
        "package": "langchain_groq",
        "extra": "groq",
        "url": "https://console.groq.com/keys",
        "note": "Fast open models",
    },
    {
        "id": "xai",
        "label": "xAI",
        "logo": "xai",
        "model": "xai:grok-4",
        "key": "XAI_API_KEY",
        "package": "langchain_xai",
        "extra": "xai",
        "url": "https://console.x.ai/",
        "note": "Grok",
    },
    {
        "id": "mistral",
        "label": "Mistral",
        "logo": "mistral",
        "model": "mistralai:mistral-large-latest",
        "key": "MISTRAL_API_KEY",
        "package": "langchain_mistralai",
        "extra": "mistral",
        "url": "https://console.mistral.ai/api-keys",
        "note": "Open weights",
    },
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "logo": "deepseek",
        "model": "deepseek:deepseek-chat",
        "key": "DEEPSEEK_API_KEY",
        "package": "langchain_deepseek",
        "extra": "deepseek",
        "url": "https://platform.deepseek.com/api_keys",
        "note": "Open weights",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter",
        "logo": "openrouter",
        "model": "openai:moonshotai/kimi-k2",
        "key": "OPENROUTER_API_KEY",
        "package": "langchain_openai",
        "extra": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "url": "https://openrouter.ai/keys",
        "note": "Kimi, GLM, and more",
    },
    {
        "id": "moonshot",
        "label": "Kimi",
        "logo": "moonshot",
        "model": "openai:kimi-k2-0905-preview",
        "key": "MOONSHOT_API_KEY",
        "package": "langchain_openai",
        "extra": "openai",
        "base_url": "https://api.moonshot.ai/v1",
        "url": "https://platform.moonshot.ai/",
        "note": "OpenAI-compatible",
    },
    {
        "id": "zhipu",
        "label": "GLM",
        "logo": "zhipu",
        "model": "openai:glm-4.6",
        "key": "ZHIPU_API_KEY",
        "package": "langchain_openai",
        "extra": "openai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "url": "https://open.bigmodel.cn/",
        "note": "OpenAI-compatible",
    },
    {
        "id": "custom",
        "label": "Custom",
        "logo": "custom",
        "model": "",
        "key": "",
        "package": "",
        "extra": "",
        "url": "",
        "note": "Your provider, key, and base URL",
    },
)
"""Model provider cards for the wizard. Key names are allowlisted env names; nothing else is written.

OpenAI-compatible presets use the `openai:` prefix with a base URL and their own key env var,
which `PAID_MEDIA_MODEL_API_KEY_ENV` hands to the client. Model ids are examples to edit.
"""


def status(root: Path) -> ActionResult:
    settings = load_settings(root)
    checks = run_doctor(settings, project_root=root)
    env = {v.name: v.is_set for v in masked_env(root)}
    accounts = read_accounts(active_accounts_path(settings, root))
    policy_file = None
    try:
        policy_file = load_write_policy_file(settings, root)
    except (ValueError, OSError):
        pass
    fixture = build_fixture_catalog()
    validated_ops = 0
    policy_issues: list[str] = []
    if policy_file is not None:
        policy, issues = policy_file.validate_against(fixture)
        validated_ops = len(policy.operations)
        policy_issues = [f"{i.tool_name}: {i.reason}" for i in issues if i.reason != "not_admitted"]
    kill_switch = settings.paid_media_kill_switch_path
    if not kill_switch.is_absolute():
        kill_switch = root / kill_switch
    model = settings.model_settings()
    caps = capabilities_for(model)
    plan = plan_selection(model, max_tools=settings.paid_media_max_selected_tools)
    failing = [c.name for c in checks if c.status == "fail"]
    detail: dict[str, JsonValue] = {
        "checks": _checks_json(checks),
        "env": env,
        "runtime": settings.paid_media_runtime,
        "model_presets": [dict(p) for p in MODEL_PRESETS],
        "model_key_env": model_key_env(settings),
        "model_key_set": bool(
            model_key_env(settings) and env.get(model_key_env(settings) or "", False)
        ),
        "model_base_url": settings.paid_media_model_base_url or "",
        "studio": {
            "installed": importlib.util.find_spec("langgraph_cli") is not None,
            "url": "https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024",
            "server_url": "http://127.0.0.1:2024",
        },
        "model": {
            "spec": model.spec,
            "provider": model.provider,
            "verified": caps.verified,
            "native_tool_search": caps.native_tool_search,
            "selection": plan.strategy.value,
            "selection_reason": plan.reason,
            "package_installed": _module_available(model.provider),
        },
        "pipeboard": {
            "token_set": settings.pipeboard_api_token is not None,
            "endpoints": {p.value: u for p, u in settings.pipeboard_endpoints().items()},
        },
        "accounts": [
            b.model_dump(mode="json", exclude={"provider_account_id"})
            | {"provider_account_id_masked": _mask_id(b.provider_account_id)}
            for b in accounts.bindings
        ],
        "accounts_path": str(active_accounts_path(settings, root).relative_to(root))
        if active_accounts_path(settings, root).is_relative_to(root)
        else str(active_accounts_path(settings, root)),
        "accounts_writable_path": str(WRITABLE_REL),
        "catalog": catalog_summary(fixture),
        "writes": {
            "enabled": settings.paid_media_writes_enabled,
            "kill_switch_engaged": kill_switch.exists(),
            "kill_switch_path": str(kill_switch),
            "released_revision": settings.paid_media_live_write_catalog_revision,
            "canary_tools": sorted(settings.live_write_canary_tools()),
            "policy_path": str(settings.paid_media_write_policy_path),
            "policy_operations": validated_ops,
            "policy_issues": policy_issues,
            "approvers": sorted(settings.approver_refs()),
            "allow_self_approval": settings.paid_media_allow_self_approval,
            "signing_key_set": settings.paid_media_approval_signing_key is not None,
        },
        "slack": {
            "transport": settings.slack_transport,
            "bot_token_set": settings.slack_bot_token is not None,
            "app_token_set": settings.slack_app_token is not None,
            "signing_secret_set": settings.slack_signing_secret is not None,
            "package_installed": importlib.util.find_spec("slack_bolt") is not None,
        },
        "self_hosted": {
            "database_url_set": settings.database_url is not None,
            "api_tokens_set": settings.paid_media_api_tokens is not None,
            "psycopg_installed": importlib.util.find_spec("psycopg") is not None,
            "api_host": settings.paid_media_api_host,
            "api_port": settings.paid_media_api_port,
        },
        "mda": {
            "cli_installed": importlib.util.find_spec("managed_deepagents") is not None,
            "langsmith_key_set": env.get("LANGSMITH_API_KEY", False),
            "agent_entry": (root / "agent.py").exists(),
            "slack_channel": (root / "channels" / "slack.py").exists(),
            "instructions": (root / "instructions.md").exists(),
        },
        "tooling": {"uv": shutil.which("uv") is not None, "python": sys.version.split()[0]},
        "pdf": next((c.status == "ok" for c in checks if c.name == "report_pdf"), False),
        "generated_at": datetime.now(UTC).isoformat(),
    }
    summary = "all checks pass" if not failing else f"failing checks: {', '.join(failing)}"
    return _result(
        "status",
        "fail" if failing else "ok",
        summary,
        detail,
        command="paid-media-agent doctor --json",
    )


WRITABLE_REL = Path("config/accounts.toml")


def _mask_id(value: str) -> str:
    return value if len(value) <= 4 else f"{value[:2]}…{value[-2:]}"


PROVIDER_MODULES: dict[str, str] = {
    "anthropic": "langchain_anthropic",
    "openai": "langchain_openai",
    "google_genai": "langchain_google_genai",
    "groq": "langchain_groq",
    "xai": "langchain_xai",
    "mistralai": "langchain_mistralai",
    "deepseek": "langchain_deepseek",
    "langsmith": "langchain_openai",
    "scripted": "paid_media_agent",
}
PROVIDER_DEFAULT_KEYS: dict[str, str] = {
    "langsmith": "LANGSMITH_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "google_genai": "GOOGLE_API_KEY",
    "groq": "GROQ_API_KEY",
    "xai": "XAI_API_KEY",
    "mistralai": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _module_available(provider: str) -> bool:
    module = PROVIDER_MODULES.get(provider)
    return module is not None and importlib.util.find_spec(module) is not None


def model_key_env(settings: Settings) -> str | None:
    """The env var that must hold the key for the configured model."""
    if settings.paid_media_model_api_key_env:
        return settings.paid_media_model_api_key_env
    return PROVIDER_DEFAULT_KEYS.get(settings.model_settings().provider)


def config_view(root: Path) -> ActionResult:
    views = [v.model_dump(mode="json") for v in masked_env(root)]
    return _result(
        "config_view",
        "ok",
        f"{sum(1 for v in views if v['is_set'])} key(s) set",
        {"keys": views, "path": str(root / ".env")},
        command="paid-media-agent config show --json",
    )


def config_set(root: Path, updates: Mapping[str, str]) -> ActionResult:
    try:
        written = write_env(root, updates)
    except EnvFileError as exc:
        return _result("config_set", "fail", str(exc))
    return _result(
        "config_set",
        "ok",
        f"updated {', '.join(written)}",
        {"keys": written},
        command="paid-media-agent config set KEY=VALUE",
    )


def generate_secret(root: Path, key: str) -> ActionResult:
    """Create a strong value for a host-owned secret and store it. The value is never returned."""
    if key == "PAID_MEDIA_APPROVAL_SIGNING_KEY":
        value = secrets.token_urlsafe(48)
    elif key == "PAID_MEDIA_API_TOKENS":
        value = f"{secrets.token_urlsafe(32)}:operator"
    else:
        return _result("generate_secret", "fail", f"{key} cannot be generated")
    write_env(root, {key: value})
    shown = value if key == "PAID_MEDIA_API_TOKENS" else ""
    detail: dict[str, JsonValue] = {"key": key}
    if shown:
        # An API token is shown once so the operator can store it in their client; it is not logged.
        detail["show_once"] = shown
        # `.env` stores `token:caller`; clients send only the token part as the bearer.
        detail["usage"] = f"Authorization: Bearer {shown.split(':', 1)[0]}"
    return _result(
        "generate_secret",
        "ok",
        f"{key} generated and stored in .env",
        detail,
        command=f"paid-media-agent config generate {key}",
    )


# ---------------------------------------------------------------- tests


def model_test(root: Path, *, invoke: Callable[[str], str] | None = None) -> ActionResult:
    settings = load_settings(root)
    try:
        model = settings.model_settings()
    except ValueError as exc:
        return _result("model_test", "fail", str(exc))
    if model.provider == "scripted":
        return _result(
            "model_test", "skipped", "scripted model needs no provider", {"spec": model.spec}
        )
    if not _module_available(model.provider):
        return _result(
            "model_test",
            "fail",
            f"provider package for {model.provider} is not installed; run uv sync --extra {model.provider.replace('_genai', '')}",
        )
    env = read_env(root)
    key_name = model_key_env(settings)
    if key_name and not env.get(key_name) and not _os_env(key_name):
        return _result(
            "model_test",
            "fail",
            f"{key_name} is not set",
            {"spec": model.spec, "missing": key_name},
        )
    started = time.monotonic()
    try:
        if invoke is None:
            from paid_media_agent.assembly import resolve_model  # noqa: PLC0415

            chat = resolve_model(
                model,
                api_key_env=settings.paid_media_model_api_key_env,
                timeout_seconds=settings.paid_media_model_timeout_seconds,
            )
            reply = _content_text(chat.invoke("Reply with the single word OK.").content)
        else:
            reply = invoke(model.spec)
    except Exception as exc:  # noqa: BLE001 - reported, never raised to the page
        return _result(
            "model_test",
            "fail",
            f"model call failed: {sanitize_exception(exc)}",
            {"spec": model.spec},
        )
    latency_ms = int((time.monotonic() - started) * 1000)
    plan = plan_selection(model, max_tools=settings.paid_media_max_selected_tools)
    return _result(
        "model_test",
        "ok",
        f"{model.spec} answered in {latency_ms} ms",
        {
            "spec": model.spec,
            "latency_ms": latency_ms,
            "selection": plan.strategy.value,
            "reply_preview": reply[:40],
        },
        command="paid-media-agent test model --json",
    )


def _content_text(content: Any) -> str:
    """Model content is a string or a list of blocks; keep only the text either way."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        ]
        return " ".join(p for p in parts if p)
    return str(content)


def _os_env(name: str) -> str | None:
    import os  # noqa: PLC0415

    return os.environ.get(name)


class LiveCatalog(BaseModel):
    """Result of a host-side live catalog load, kept separate from the model-facing runtime."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    catalog: AuthorizedToolCatalog
    loader: Any


LiveLoader = Callable[[Settings, Path], "asyncio.Future[LiveCatalog] | Any"]


async def _load_live(settings: Settings, root: Path) -> LiveCatalog:
    from paid_media_agent.runtime.self_hosted import load_catalog  # noqa: PLC0415

    loaded = await load_catalog(settings, project_root=root)
    return LiveCatalog(catalog=loaded.catalog, loader=loaded.provider)


def pipeboard_test(
    root: Path, *, loader: Callable[[Settings, Path], Any] | None = None
) -> ActionResult:
    settings = load_settings(root)
    if settings.pipeboard_api_token is None:
        return _result(
            "pipeboard_test",
            "warn",
            "PIPEBOARD_API_TOKEN is not set; the fixture catalog is active",
            {"catalog": catalog_summary(build_fixture_catalog())},
            command="paid-media-agent test pipeboard --json",
        )
    try:
        live = asyncio.run(_load_live(settings, root)) if loader is None else loader(settings, root)
    except Exception as exc:  # noqa: BLE001
        return _result("pipeboard_test", "fail", f"catalog load failed: {sanitize_exception(exc)}")
    summary = catalog_summary(live.catalog)
    empty = (
        [p for p, counts in summary["platforms"].items() if counts.get("read", 0) == 0]
        if isinstance(summary["platforms"], dict)
        else []
    )
    missing = [p.value for p in PIPEBOARD_PLATFORMS if p.value not in (summary["platforms"] or {})]
    status_value: Status = "ok" if not missing and not empty else "warn"
    note = ""
    if missing:
        note = f"; no tools loaded for {', '.join(missing)} (not connected in Pipeboard, or endpoint unreachable)"
    return _result(
        "pipeboard_test",
        status_value,
        f"live catalog {live.catalog.revision}: {summary['read']} read, {summary['mutation']} admitted mutation, {summary['denied']} denied{note}",
        {"catalog": summary},
        command="paid-media-agent test pipeboard --json",
    )


_LISTING_TOOL_RE = re.compile(r"^(list|get)_.*(customers|ad_accounts|accounts)$|^list_ad_accounts$")
_ID_KEYS = ("customer_id", "account_id", "ad_account_id", "id")
_NAME_KEYS = ("descriptive_name", "account_name", "name", "title")
_CURRENCY_KEYS = ("currency_code", "currency", "account_currency")
_TZ_KEYS = ("time_zone", "timezone", "timezone_name")


def _extract_accounts(platform: str, payload: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    def visit(node: Any) -> None:
        if isinstance(node, list):
            for item in node:
                visit(item)
            return
        if not isinstance(node, dict):
            return
        identifier = next((str(node[k]) for k in _ID_KEYS if node.get(k) not in (None, "")), None)
        if identifier is not None and any(
            k in node for k in (*_NAME_KEYS, *_CURRENCY_KEYS, *_TZ_KEYS)
        ):
            rows.append(
                {
                    "platform": platform,
                    "provider_account_id": identifier,
                    "name": next((str(node[k]) for k in _NAME_KEYS if node.get(k)), identifier),
                    "currency": next((str(node[k]) for k in _CURRENCY_KEYS if node.get(k)), ""),
                    "timezone": next((str(node[k]) for k in _TZ_KEYS if node.get(k)), ""),
                }
            )
            return
        for value in node.values():
            visit(value)

    visit(payload)
    unique: dict[str, dict[str, str]] = {}
    for row in rows:
        unique.setdefault(row["provider_account_id"], row)
    return list(unique.values())


def _annotate_mapped(
    root: Path, settings: Settings, rows: list[dict[str, str]]
) -> list[dict[str, str]]:
    registry = read_accounts(active_accounts_path(settings, root))
    by_id = {(b.platform.value, b.provider_account_id): b.alias for b in registry.bindings}
    return [
        {**row, "mapped_alias": by_id.get((row["platform"], row["provider_account_id"]), "")}
        for row in rows
    ]


def accounts_discover(
    root: Path, *, loader: Callable[[Settings, Path], Any] | None = None
) -> ActionResult:
    """Host-side discovery of provider accounts. The model never sees these ids."""
    settings = load_settings(root)
    if settings.pipeboard_api_token is None and not settings.direct_platforms():
        fixture_rows: list[dict[str, str]] = []
        for platform in PIPEBOARD_PLATFORMS:
            data = load_fixture_dataset(platform)
            fixture_rows.append(
                {
                    "platform": platform.value,
                    "provider_account_id": str(data["account_id"]),
                    "name": f"Fixture {platform.value} account",
                    "currency": str(data["currency"]),
                    "timezone": str(data["timezone"]),
                }
            )
        return _result(
            "accounts_discover",
            "warn",
            "no Pipeboard token; showing fixture accounts",
            {"accounts": _annotate_mapped(root, settings, fixture_rows), "source": "fixture"},
            command="paid-media-agent accounts discover --json",
        )
    try:
        live = asyncio.run(_load_live(settings, root)) if loader is None else loader(settings, root)
    except Exception as exc:  # noqa: BLE001
        return _result(
            "accounts_discover", "fail", f"catalog load failed: {sanitize_exception(exc)}"
        )
    from paid_media_agent.tools.direct import direct_read_providers  # noqa: PLC0415
    from paid_media_agent.tools.pipeboard import invoke_mcp_tool  # noqa: PLC0415

    direct_providers = direct_read_providers(settings)
    rows: list[dict[str, str]] = []
    used: list[str] = []
    errors: list[str] = []
    for entry in live.catalog.entries:
        if (
            entry.read_only_hint is not True
            or not _LISTING_TOOL_RE.match(entry.name)
            or entry.account_arg is not None
        ):
            continue
        try:
            if entry.platform in direct_providers:
                result = asyncio.run(direct_providers[entry.platform].call_read(entry, {}))
                payload: Any = result.payload
            else:
                tool = (
                    live.loader.langchain_tool(entry.qualified_name)
                    if hasattr(live.loader, "langchain_tool")
                    else None
                )
                if tool is None:
                    continue
                payload = asyncio.run(invoke_mcp_tool(tool, {}, timeout=60))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{entry.qualified_name}: {sanitize_exception(exc)}")
            continue
        used.append(entry.qualified_name)
        rows.extend(_extract_accounts(entry.platform.value, payload))
    status_value: Status = "ok" if rows else "warn"
    summary = (
        f"{len(rows)} account(s) from {len(used)} listing tool(s)"
        if rows
        else "no accounts discovered; connect platforms in Pipeboard first"
    )
    return _result(
        "accounts_discover",
        status_value,
        summary,
        {
            "accounts": _annotate_mapped(root, settings, rows),
            "tools": used,
            "errors": errors,
            "source": "pipeboard",
        },
        command="paid-media-agent accounts discover --json",
    )


def accounts_list(root: Path) -> ActionResult:
    settings = load_settings(root)
    path = active_accounts_path(settings, root)
    registry = read_accounts(path)
    rows = [
        b.model_dump(mode="json", exclude={"provider_account_id"})
        | {"provider_account_id_masked": _mask_id(b.provider_account_id)}
        for b in registry.bindings
    ]
    return _result(
        "accounts_list",
        "ok" if rows else "warn",
        f"{len(rows)} alias(es) in {path.name}",
        {"accounts": rows, "path": str(path)},
        command="paid-media-agent accounts list --json",
    )


def accounts_add(
    root: Path, *, alias: str, platform: str, provider_account_id: str, currency: str, timezone: str
) -> ActionResult:
    settings = load_settings(root)
    try:
        binding = AccountBinding(
            alias=alias,
            platform=Platform(platform),
            provider_account_id=provider_account_id.strip(),
            currency=currency.upper().strip(),
            timezone=timezone.strip(),
        )
        target = writable_accounts_path(root)
        registry = add_account(target, binding, seed_from=active_accounts_path(settings, root))
    except (ValueError, AccountsFileError) as exc:
        return _result("accounts_add", "fail", sanitize_exception(exc))
    if active_accounts_path(settings, root) != target:
        write_env(root, {"PAID_MEDIA_ACCOUNT_CONFIG_PATH": str(WRITABLE_REL)})
    return _result(
        "accounts_add",
        "ok",
        f"alias {alias} mapped ({len(registry.bindings)} total)",
        {"aliases": list(registry.aliases()), "path": str(WRITABLE_REL)},
        command=f"paid-media-agent accounts add {alias} --platform {platform} --id <provider-id> --currency {currency} --timezone {timezone}",
    )


def accounts_remove(root: Path, alias: str) -> ActionResult:
    settings = load_settings(root)
    path = active_accounts_path(settings, root)
    if path != writable_accounts_path(root):
        return _result(
            "accounts_remove",
            "fail",
            "the active accounts file is an example; add an alias first to create config/accounts.toml",
        )
    try:
        registry = remove_account(path, alias)
    except AccountsFileError as exc:
        return _result("accounts_remove", "fail", str(exc))
    return _result(
        "accounts_remove",
        "ok",
        f"alias {alias} removed",
        {"aliases": list(registry.aliases())},
        command=f"paid-media-agent accounts remove {alias}",
    )


def catalog_show(
    root: Path, *, live: bool = False, loader: Callable[[Settings, Path], Any] | None = None
) -> ActionResult:
    settings = load_settings(root)
    if live and settings.pipeboard_api_token is not None:
        try:
            loaded = (
                asyncio.run(_load_live(settings, root))
                if loader is None
                else loader(settings, root)
            )
        except Exception as exc:  # noqa: BLE001
            return _result(
                "catalog_show", "fail", f"catalog load failed: {sanitize_exception(exc)}"
            )
        catalog = loaded.catalog
    else:
        catalog = build_fixture_catalog()
    entries = [
        {
            "name": e.qualified_name,
            "platform": e.platform.value,
            "class": e.tool_class.value,
            "reason": e.policy.reason,
            "description": e.description[:120],
        }
        for e in catalog.entries
    ]
    return _result(
        "catalog_show",
        "ok",
        f"{catalog.source} catalog {catalog.revision}",
        {"catalog": catalog_summary(catalog), "entries": entries},
        command="paid-media-agent catalog show --json",
    )


def policy_validate(
    root: Path, *, live: bool = False, loader: Callable[[Settings, Path], Any] | None = None
) -> ActionResult:
    settings = load_settings(root)
    try:
        policy_file = load_write_policy_file(settings, root)
    except (ValueError, OSError) as exc:
        return _result(
            "policy_validate", "fail", f"policy file unreadable: {sanitize_exception(exc)}"
        )
    if policy_file is None:
        return _result(
            "policy_validate",
            "warn",
            "no write policy file; the fixture policy applies",
            command="paid-media-agent policy validate --json",
        )
    if live and settings.pipeboard_api_token is not None:
        try:
            loaded = (
                asyncio.run(_load_live(settings, root))
                if loader is None
                else loader(settings, root)
            )
        except Exception as exc:  # noqa: BLE001
            return _result(
                "policy_validate", "fail", f"catalog load failed: {sanitize_exception(exc)}"
            )
        catalog = loaded.catalog
    else:
        catalog = build_fixture_catalog()
    policy, issues = policy_file.validate_against(catalog)
    blocking = [i for i in issues if i.reason != "not_admitted"]
    detail: dict[str, JsonValue] = {
        "catalog": catalog.source,
        "admitted": [op.tool_name for op in policy.operations],
        "issues": [{"tool": i.tool_name, "reason": i.reason} for i in issues],
        "denied_mutations": sorted(
            e.qualified_name for e in catalog.denied_entries() if e.read_only_hint is False
        ),
    }
    return _result(
        "policy_validate",
        "warn" if blocking else "ok",
        f"{len(policy.operations)} operation(s) admitted; {len(blocking)} blocking issue(s)",
        detail,
        command="paid-media-agent policy validate --live --json"
        if live
        else "paid-media-agent policy validate --json",
    )


def slack_test(root: Path, *, client_factory: Callable[[str], Any] | None = None) -> ActionResult:
    settings = load_settings(root)
    if settings.slack_bot_token is None:
        return _result("slack_test", "fail", "SLACK_BOT_TOKEN is not set")
    if importlib.util.find_spec("slack_sdk") is None:
        return _result("slack_test", "fail", "slack extra not installed; run uv sync --extra slack")
    try:
        if client_factory is None:
            from slack_sdk import WebClient  # noqa: PLC0415

            client_factory = lambda token: WebClient(token=token)  # noqa: E731
        bot = client_factory(settings.slack_bot_token.get_secret_value()).auth_test()
        detail: dict[str, JsonValue] = {
            "team": bot.get("team"),
            "bot_user": bot.get("user"),
            "transport": settings.slack_transport,
        }
        if settings.slack_transport == "socket_mode":
            if settings.slack_app_token is None:
                return _result(
                    "slack_test", "fail", "SLACK_APP_TOKEN is required for Socket Mode", detail
                )
            app_token = settings.slack_app_token.get_secret_value()
            client_factory(app_token).apps_connections_open(app_token=app_token)
            detail["socket_mode"] = "connection ticket issued"
        elif settings.slack_signing_secret is None:
            return _result(
                "slack_test",
                "fail",
                "SLACK_SIGNING_SECRET is required for the HTTP transport",
                detail,
            )
    except Exception as exc:  # noqa: BLE001
        return _result(
            "slack_test", "fail", f"Slack rejected the credentials: {sanitize_exception(exc)}"
        )
    return _result(
        "slack_test",
        "ok",
        f"connected to {detail.get('team')} as {detail.get('bot_user')}",
        detail,
        command="paid-media-agent test slack --json",
    )


def database_test(root: Path, *, connect: Callable[[str], Any] | None = None) -> ActionResult:
    settings = load_settings(root)
    if settings.database_url is None:
        return _result(
            "database_test",
            "warn",
            "DATABASE_URL is not set; the self-hosted runtime uses in-memory state",
        )
    if importlib.util.find_spec("psycopg") is None:
        return _result(
            "database_test", "fail", "psycopg not installed; run uv sync --extra self-host"
        )
    try:
        if connect is None:
            import psycopg  # noqa: PLC0415

            with psycopg.connect(
                settings.database_url.get_secret_value(), connect_timeout=10
            ) as conn:
                version = conn.execute("SELECT version()").fetchone()
        else:
            version = connect(settings.database_url.get_secret_value())
    except Exception as exc:  # noqa: BLE001
        return _result("database_test", "fail", f"connection failed: {sanitize_exception(exc)}")
    return _result(
        "database_test",
        "ok",
        "Postgres reachable",
        {"version": str(version[0])[:60] if version else ""},
        command="paid-media-agent test db --json",
    )


def mda_check(root: Path) -> ActionResult:
    settings = load_settings(root)
    env = read_env(root)
    items: dict[str, JsonValue] = {
        "cli_installed": importlib.util.find_spec("managed_deepagents") is not None,
        "langsmith_key_set": bool(env.get("LANGSMITH_API_KEY") or _os_env("LANGSMITH_API_KEY")),
        "agent_entry": (root / "agent.py").exists(),
        "instructions": (root / "instructions.md").exists(),
        "skills": (root / "skills").is_dir(),
        "slack_channel": (root / "channels" / "slack.py").exists(),
        "identity": (root / "identity.py").exists(),
        "sandbox_declared": (root / "sandbox" / "__init__.py").exists(),
        "sandbox_snapshot": settings.paid_media_sandbox_snapshot or "",
        "model": settings.model_settings().spec,
        "model_package": _module_available(settings.model_settings().provider),
        "provider_key_set": _provider_key_set(settings, env),
        "import_smoke": _agent_import_smoke(root),
        "deploy_command": "uv run mda deploy .",
        "dev_command": "uv run mda dev",
    }
    blocking = [
        k
        for k in (
            "cli_installed",
            "langsmith_key_set",
            "agent_entry",
            "model_package",
            "provider_key_set",
        )
        if not items[k]
    ]
    if items["slack_channel"] and not items["identity"]:
        # MDA refuses to build an ingress channel without a root identity declaration.
        blocking.append("identity")
    if items["import_smoke"] != "ok":
        blocking.append("import_smoke")
    if items["sandbox_snapshot"] and not items["sandbox_declared"]:
        # Our runtimes read the snapshot from .env; MDA reads only the literal in sandbox/__init__.py.
        blocking.append("sandbox_declared (run `paid-media-agent sandbox use <name>`)")
    summary = "ready to deploy" if not blocking else f"blocked by {', '.join(blocking)}"
    return _result(
        "mda_check",
        "ok" if not blocking else "warn",
        summary,
        items,
        command="paid-media-agent mda check --json",
    )


def _provider_key_set(settings: Settings, env: Mapping[str, str]) -> bool:
    key_name = model_key_env(settings)
    if key_name is None:
        return True
    return bool(env.get(key_name) or _os_env(key_name))


def _agent_import_smoke(root: Path) -> str:
    """Import agent.py in a subprocess so a broken entry cannot take the console down."""
    try:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and script, no user input
            [sys.executable, "-c", "import agent; print(agent.agent.config['name'])"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"failed: {sanitize_exception(exc)}"
    if completed.returncode != 0:
        return "failed: " + sanitize_exception(RuntimeError(completed.stderr.strip()[-300:]))
    return "ok"


def demo_run(root: Path, *, with_proposal: bool = False) -> ActionResult:
    from paid_media_agent.cli import run_demo  # noqa: PLC0415

    settings = Settings(paid_media_model="scripted:demo", paid_media_allow_self_approval=True)
    try:
        result = asyncio.run(run_demo(settings, with_proposal=with_proposal, root=root))
    except Exception as exc:  # noqa: BLE001
        return _result("demo_run", "fail", f"demo failed: {sanitize_exception(exc)}")
    detail: dict[str, JsonValue] = {
        "answer": result["answer"],
        "audit": result["audit"],
        "catalog_revision": result["catalog_revision"],
    }
    if with_proposal:
        detail["proposal"] = result.get("proposal")
        detail["receipt"] = result.get("receipt")
        detail["receipt_message"] = result.get("receipt_message")
    return _result(
        "demo_run",
        "ok",
        "fixture demo completed",
        detail,
        command="paid-media-agent demo" + (" --with-proposal" if with_proposal else ""),
    )


MAX_QUESTION_CHARS = 2000


def ask_question(root: Path, question: str, *, model: Any | None = None) -> ActionResult:
    """Run one question through the local runtime with the configured model."""
    settings = load_settings(root)
    text = question.strip()
    if not text or len(text) > MAX_QUESTION_CHARS:
        return _result("ask", "fail", "question must be 1 to 2000 characters")
    try:
        from langchain_core.runnables import RunnableConfig  # noqa: PLC0415

        from paid_media_agent.assembly import resolve_model  # noqa: PLC0415
        from paid_media_agent.runtime.local import build_local_runtime  # noqa: PLC0415

        chat = (
            model
            if model is not None
            else resolve_model(
                settings.model_settings(),
                api_key_env=settings.paid_media_model_api_key_env,
                timeout_seconds=settings.paid_media_model_timeout_seconds,
            )
        )
        from paid_media_agent.runtime.sandbox import build_backend  # noqa: PLC0415

        runtime = build_local_runtime(
            settings,
            project_root=root,
            model=chat,
            backend=build_backend(settings, project_root=root),
        )
        config = RunnableConfig(
            configurable={
                "thread_id": f"console-{secrets.token_hex(4)}",
                "caller_ref": "local-user",
            }
        )
        state = asyncio.run(
            runtime.graph.ainvoke({"messages": [{"role": "user", "content": text}]}, config=config)
        )
        answer_text = _content_text(state["messages"][-1].content)
    except Exception as exc:  # noqa: BLE001 - reported, never raised to the page
        return _result("ask", "fail", f"run failed: {sanitize_exception(exc)}")
    if answer_text.startswith("Model call failed"):
        # The retry middleware turns provider failures into a message; surface them as a failure.
        return _result("ask", "fail", sanitize_exception(RuntimeError(answer_text)))
    return _result(
        "ask",
        "ok",
        "answered",
        {
            "answer": answer_text[:6000],
            "selection": runtime.components.metadata.selection.strategy.value,
            "catalog_revision": runtime.catalog.revision,
        },
        command='uv run python examples/ask.py "..."',
    )


def kill_switch_set(root: Path, *, engaged: bool, confirmed: bool = False) -> ActionResult:
    settings = load_settings(root)
    path = settings.paid_media_kill_switch_path
    if not path.is_absolute():
        path = root / path
    if engaged:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"engaged {datetime.now(UTC).isoformat()}\n", encoding="utf-8")
        return _result(
            "kill_switch",
            "ok",
            "kill switch engaged: every execution is refused",
            {"path": str(path), "engaged": True},
            command="paid-media-agent writes kill-switch on",
        )
    if not confirmed:
        return _result(
            "kill_switch",
            "fail",
            "removing the kill switch requires confirmation",
            {"path": str(path), "engaged": path.exists()},
        )
    if path.exists():
        path.unlink()
    return _result(
        "kill_switch",
        "ok",
        "kill switch cleared",
        {"path": str(path), "engaged": False},
        command="paid-media-agent writes kill-switch off --yes",
    )


def snapshot_check(root: Path) -> ActionResult:
    checks = run_snapshot_checks(root)
    failing = [c.name for c in checks if c.status == "fail"]
    return _result(
        "snapshot_check",
        "fail" if failing else "ok",
        "snapshot contract passes" if not failing else f"failing: {', '.join(failing)}",
        {"checks": _checks_json(checks)},
        command="paid-media-agent doctor --snapshot",
    )


def as_json(result: ActionResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2, default=str)


# ---------------------------------------------------------------- sandbox

SANDBOX_DECLARATION = '''"""Managed sandbox for Managed Deep Agents. Generated by `paid-media-agent sandbox use`.

MDA reads this file statically, so the snapshot name must be a literal. Our own runtimes read
`PAID_MEDIA_SANDBOX_SNAPSHOT` from `.env`; `mda check` reports when the two disagree.
"""

from managed_deepagents import define_sandbox

sandbox = define_sandbox({argument}, idle_ttl_seconds=1800)
'''
SNAPSHOT_FS_GIB = 32
"""Snapshot filesystem size; the platform base image alone needs 16 GiB."""
SNAPSHOT_BUILD_TIMEOUT = 1800
"""The SDK builds inside a builder sandbox and applies this to the build command itself."""
SNAPSHOT_HTTP_TIMEOUT = 120.0
"""Capturing a snapshot is one slow HTTP call; the SDK client default of 10 s cuts it off."""


def sandbox_use(root: Path, name: str) -> ActionResult:
    """Point both worlds at one snapshot: `.env` for our runtimes, `sandbox/__init__.py` for MDA.

    `name` is a snapshot id (preferred, immutable) or a snapshot name.
    """
    from paid_media_agent.runtime.sandbox import snapshot_reference  # noqa: PLC0415

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}", name):
        return _result("sandbox_use", "fail", "snapshot must be alphanumeric with . _ -")
    ((key, value),) = snapshot_reference(name).items()
    write_env(root, {"PAID_MEDIA_SANDBOX_SNAPSHOT": name})
    (root / "sandbox" / "__init__.py").write_text(
        SANDBOX_DECLARATION.format(argument=f"{key}={value!r}"), encoding="utf-8"
    )
    return _result(
        "sandbox_use",
        "ok",
        f"snapshot {name} set in .env and declared in sandbox/__init__.py",
        {"snapshot": name},
        command=f"paid-media-agent sandbox use {name}",
    )


def sandbox_publish(
    root: Path,
    *,
    name: str,
    fs_gib: int = SNAPSHOT_FS_GIB,
    log: Callable[[str], None] | None = None,
) -> ActionResult:
    """Build sandbox/Dockerfile into a LangSmith snapshot, then `sandbox_use` it.

    LangSmith builds the image; no local Docker is involved. The build context holds only the
    Dockerfile, never `.env`, skills, or wiki pages.
    """
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    from langsmith.sandbox import SandboxClient  # noqa: PLC0415

    dockerfile = root / "sandbox" / "Dockerfile"
    if not dockerfile.exists():
        return _result("sandbox_publish", "fail", "sandbox/Dockerfile is missing")
    client = SandboxClient(timeout=SNAPSHOT_HTTP_TIMEOUT)
    try:
        with tempfile.TemporaryDirectory() as context:
            shutil.copy(dockerfile, Path(context) / "Dockerfile")
            snapshot = client.create_snapshot_from_dockerfile(
                name,
                Path(context) / "Dockerfile",
                fs_capacity_bytes=fs_gib * 1024**3,
                context=context,
                on_build_log=log,
                timeout=SNAPSHOT_BUILD_TIMEOUT,
            )
        snapshot = client.wait_for_snapshot(snapshot.id, timeout=SNAPSHOT_BUILD_TIMEOUT)
    except Exception as exc:  # noqa: BLE001 - the SDK also surfaces raw transport timeouts
        return _result(
            "sandbox_publish", "fail", f"snapshot build failed: {sanitize_exception(exc)}"
        )
    status = str(getattr(snapshot.status, "value", snapshot.status))
    if status != "ready":
        return _result(
            "sandbox_publish", "fail", f"snapshot {name} is {status}: {snapshot.status_message}"
        )
    used = sandbox_use(root, str(snapshot.id))
    return _result(
        "sandbox_publish",
        used.status,
        f"snapshot {name} ready; {used.summary}",
        {"snapshot": name, "snapshot_id": str(snapshot.id)},
        command=f"paid-media-agent sandbox publish --name {name}",
    )


def sandbox_test(root: Path) -> ActionResult:
    """Open one sandbox from the configured snapshot, run the probe, and delete it."""
    from paid_media_agent.runtime.sandbox import (  # noqa: PLC0415
        SandboxError,
        open_sandbox,
        probe_sandbox,
    )

    settings = load_settings(root)
    command = "paid-media-agent sandbox test --json"
    if not (_os_env("LANGSMITH_API_KEY") or read_env(root).get("LANGSMITH_API_KEY")):
        return _result("sandbox_test", "warn", "LANGSMITH_API_KEY is not set", command=command)
    try:
        sandbox = open_sandbox(settings)
    except SandboxError as exc:
        return _result("sandbox_test", "fail", sanitize_exception(exc), command=command)
    try:
        checks = probe_sandbox(sandbox, root)
    finally:
        sandbox.close()
    failing = [c.name for c in checks if c.status == "fail"]
    detail: dict[str, JsonValue] = {
        "snapshot": settings.paid_media_sandbox_snapshot or "platform default",
        "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks],
    }
    return _result(
        "sandbox_test",
        "fail" if failing else "ok",
        "sandbox can host the agent" if not failing else f"failing: {', '.join(failing)}",
        detail,
        command=command,
    )
