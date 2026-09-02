"""Setup console primitives: env file, accounts file, routes, and the process manager."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from paid_media_agent.admin import actions
from paid_media_agent.admin.accounts_file import (
    AccountsFileError,
    add_account,
    read_accounts,
    remove_account,
)
from paid_media_agent.admin.envfile import EnvFileError, masked_env, read_env, write_env
from paid_media_agent.admin.processes import PROCESS_TEMPLATES, ProcessError, ProcessManager
from paid_media_agent.admin.routes import build_routes
from paid_media_agent.config import AccountBinding
from paid_media_agent.domain.common import Platform


@pytest.fixture
def workspace(tmp_path: Path, project_root: Path) -> Path:
    """A throwaway project copy with the files the console reads and writes."""
    for name in ("instructions.md", ".env.example", "agent.py"):
        shutil.copy(project_root / name, tmp_path / name)
    shutil.copytree(project_root / "skills", tmp_path / "skills")
    shutil.copytree(project_root / "config", tmp_path / "config")
    shutil.copytree(project_root / "channels", tmp_path / "channels")
    (tmp_path / "workspace").mkdir()
    return tmp_path


def test_env_write_is_allowlisted_masked_and_private(workspace: Path) -> None:
    written = write_env(
        workspace,
        {"PAID_MEDIA_MODEL": "openai:gpt-5.5", "OPENAI_API_KEY": "sk-test-value-1234567890abcdef"},
    )
    assert set(written) == {"PAID_MEDIA_MODEL", "OPENAI_API_KEY"}
    env_file = workspace / ".env"
    assert oct(env_file.stat().st_mode & 0o777) == "0o600"
    text = env_file.read_text()
    assert "PAID_MEDIA_MODEL=openai:gpt-5.5" in text and "# Runtime" in text, (
        "seeded from .env.example, comments kept"
    )
    values = read_env(workspace)
    assert values["OPENAI_API_KEY"] == "sk-test-value-1234567890abcdef"
    views = {v.name: v for v in masked_env(workspace)}
    assert views["OPENAI_API_KEY"].is_set and views["OPENAI_API_KEY"].value == "••••••••"
    assert views["PAID_MEDIA_MODEL"].value == "openai:gpt-5.5"
    with pytest.raises(EnvFileError):
        write_env(workspace, {"NOT_A_KEY": "x"})
    with pytest.raises(EnvFileError):
        write_env(workspace, {"PAID_MEDIA_MODEL": "a\nb"})
    write_env(workspace, {"PAID_MEDIA_APPROVER_IDS": "slack:T1:U1, api-user #ops"})
    assert read_env(workspace)["PAID_MEDIA_APPROVER_IDS"] == "slack:T1:U1, api-user #ops"


def test_accounts_file_seeds_from_example_and_rejects_duplicates(workspace: Path) -> None:
    target = workspace / "config" / "accounts.toml"
    example = workspace / "config" / "accounts.example.toml"
    binding = AccountBinding(
        alias="google-main",
        platform=Platform.GOOGLE_ADS,
        provider_account_id="123-456",
        currency="USD",
        timezone="UTC",
    )
    registry = add_account(target, binding, seed_from=example)
    assert "google-main" in registry.aliases() and "demo-google" in registry.aliases()
    assert read_accounts(target).resolve("google-main") is not None
    with pytest.raises(AccountsFileError):
        add_account(
            target,
            AccountBinding(
                alias="other",
                platform=Platform.GOOGLE_ADS,
                provider_account_id="123-456",
                currency="USD",
                timezone="UTC",
            ),
        )
    registry = remove_account(target, "demo-google")
    assert "demo-google" not in registry.aliases()
    with pytest.raises(AccountsFileError):
        remove_account(target, "demo-google")


def test_status_and_routes_reflect_configuration(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "PIPEBOARD_API_TOKEN",
        "SLACK_BOT_TOKEN",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    result = actions.status(workspace)
    assert result.action == "status"
    assert result.detail["pipeboard"]["token_set"] is False
    routes = {r.id: r for r in build_routes(result.detail)}
    assert list(routes) == ["local", "pipeboard", "slack", "mda", "self_hosted", "writes"]
    statuses = {s.id: s.status for s in routes["pipeboard"].steps}
    assert statuses["pb_token"] == "todo" and statuses["pb_test"] == "blocked"
    assert all("--json" in s.cli or s.cli for s in routes["local"].steps)

    write_env(
        workspace,
        {
            "PAID_MEDIA_MODEL": "anthropic:claude-sonnet-4-6",
            "ANTHROPIC_API_KEY": "sk-ant-" + "b" * 30,
            "PIPEBOARD_API_TOKEN": "pb_" + "c" * 20,
        },
    )
    result = actions.status(workspace)
    routes = {r.id: r for r in build_routes(result.detail)}
    assert {s.id: s.status for s in routes["local"].steps}["model"] == "done"
    assert {s.id: s.status for s in routes["pipeboard"].steps}["pb_test"] == "todo"
    assert result.detail["model"]["selection"] == "provider_native"
    assert "sk-ant-" not in actions.as_json(result)


def test_fixture_discovery_and_alias_mapping_switch_the_active_file(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("PIPEBOARD_API_TOKEN", raising=False)
    discovered = actions.accounts_discover(workspace)
    assert discovered.status == "warn" and discovered.detail["source"] == "fixture"
    rows = discovered.detail["accounts"]
    assert {r["platform"] for r in rows} == {"google_ads", "meta_ads", "reddit_ads"}
    assert {r["mapped_alias"] for r in rows} == {"demo-google", "demo-meta", "demo-reddit"}
    added = actions.accounts_add(
        workspace,
        alias="google-main",
        platform="google_ads",
        provider_account_id="fixture-google-0002",
        currency="usd",
        timezone="America/New_York",
    )
    assert added.ok, added.summary
    assert read_env(workspace)["PAID_MEDIA_ACCOUNT_CONFIG_PATH"] == "config/accounts.toml"
    listed = actions.accounts_list(workspace)
    aliases = {a["alias"] for a in listed.detail["accounts"]}
    assert "google-main" in aliases and "demo-google" in aliases
    assert all("provider_account_id" not in a for a in listed.detail["accounts"]), (
        "ids are masked in views"
    )
    assert actions.accounts_remove(workspace, "google-main").ok


def test_live_discovery_parses_listing_tools(workspace: Path) -> None:
    write_env(workspace, {"PIPEBOARD_API_TOKEN": "pb_" + "d" * 20})
    from langchain_core.tools import StructuredTool

    from paid_media_agent.tools.catalog import RawTool, build_authorized_catalog

    raw = [
        RawTool(
            platform="google_ads",
            name="list_google_ads_customers",
            description="list",
            input_schema={"type": "object", "properties": {}},
            annotations={"readOnlyHint": True},
        ),
        RawTool(
            platform="meta_ads",
            name="get_ad_accounts",
            description="list",
            input_schema={"type": "object", "properties": {}},
            annotations={"readOnlyHint": True},
        ),
    ]
    catalog = build_authorized_catalog(raw, source="pipeboard")

    async def google(**kwargs: object) -> str:
        return '{"customers": [{"customer_id": "111-222", "descriptive_name": "Acme Search", "currency_code": "USD", "time_zone": "America/Chicago"}]}'

    async def meta(**kwargs: object) -> str:
        return '{"data": [{"id": "act_999", "name": "Acme Social", "currency": "EUR"}]}'

    tools = {
        "google_ads__list_google_ads_customers": StructuredTool(
            name="list_google_ads_customers",
            description="d",
            args_schema={"type": "object", "properties": {}},
            coroutine=google,
        ),
        "meta_ads__get_ad_accounts": StructuredTool(
            name="get_ad_accounts",
            description="d",
            args_schema={"type": "object", "properties": {}},
            coroutine=meta,
        ),
    }

    class Loader:
        def langchain_tool(self, name: str) -> StructuredTool | None:
            return tools.get(name)

    result = actions.accounts_discover(
        workspace, loader=lambda _s, _r: actions.LiveCatalog(catalog=catalog, loader=Loader())
    )
    assert result.ok, result.summary
    rows = {r["provider_account_id"]: r for r in result.detail["accounts"]}
    assert (
        rows["111-222"]["name"] == "Acme Search"
        and rows["111-222"]["timezone"] == "America/Chicago"
    )
    assert rows["act_999"]["currency"] == "EUR" and rows["act_999"]["platform"] == "meta_ads"


def test_policy_validate_and_kill_switch(workspace: Path) -> None:
    result = actions.policy_validate(workspace)
    assert result.ok and len(result.detail["admitted"]) == 6
    engaged = actions.kill_switch_set(workspace, engaged=True)
    assert engaged.ok and (workspace / "workspace" / "KILL_SWITCH").exists()
    refused = actions.kill_switch_set(workspace, engaged=False)
    assert refused.status == "fail"
    cleared = actions.kill_switch_set(workspace, engaged=False, confirmed=True)
    assert cleared.ok and not (workspace / "workspace" / "KILL_SWITCH").exists()


def test_slack_and_database_tests_never_leak_and_use_injected_clients(workspace: Path) -> None:
    assert actions.slack_test(workspace).status == "fail"
    write_env(
        workspace, {"SLACK_BOT_TOKEN": "xoxb-" + "e" * 20, "SLACK_APP_TOKEN": "xapp-" + "f" * 20}
    )
    seen: list[str] = []

    class Client:
        def __init__(self, token: str) -> None:
            seen.append(token)

        def auth_test(self) -> dict[str, str]:
            return {"team": "Acme", "user": "paid-media"}

        def apps_connections_open(self, app_token: str) -> dict[str, bool]:
            assert app_token.startswith("xapp-")
            return {"ok": True}

    result = actions.slack_test(workspace, client_factory=Client)
    assert result.ok and result.detail["team"] == "Acme"
    assert "xoxb-" not in actions.as_json(result)
    assert actions.database_test(workspace).status == "warn"
    write_env(workspace, {"DATABASE_URL": "postgresql://user:pw@localhost/db"})
    result = actions.database_test(workspace, connect=lambda _url: ("PostgreSQL 16.1",))
    assert result.ok and "pw@" not in actions.as_json(result)


def test_generate_secret_shows_api_token_once_only(workspace: Path) -> None:
    signing = actions.generate_secret(workspace, "PAID_MEDIA_APPROVAL_SIGNING_KEY")
    assert signing.ok and "show_once" not in signing.detail
    api = actions.generate_secret(workspace, "PAID_MEDIA_API_TOKENS")
    assert api.ok and api.detail["show_once"].endswith(":operator")
    assert read_env(workspace)["PAID_MEDIA_API_TOKENS"] == api.detail["show_once"]
    assert actions.generate_secret(workspace, "PAID_MEDIA_MODEL").status == "fail"


def test_mda_check_runs_import_smoke(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    result = actions.mda_check(workspace)
    assert result.detail["cli_installed"] is True and result.detail["agent_entry"] is True
    assert result.detail["import_smoke"] == "ok", result.detail
    assert "langsmith_key_set" in result.summary


def test_process_manager_uses_fixed_templates(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(
        PROCESS_TEMPLATES, "serve", (sys.executable, "-c", "print('hello from serve')")
    )
    manager = ProcessManager(workspace)
    with pytest.raises(ProcessError):
        manager.start("not-a-template")
    with pytest.raises(ProcessError):
        manager.start("mda-deploy")  # confirmation required
    view = manager.start("serve")
    assert view.command == "uv run paid-media-agent serve"
    manager._procs["serve"].wait(timeout=30)  # noqa: SLF001
    view = manager.view("serve")
    assert not view.running and view.returncode == 0 and "hello from serve" in view.log_tail
    assert os.path.exists(workspace / "workspace" / "logs" / "serve.log")
    manager.stop_all()
