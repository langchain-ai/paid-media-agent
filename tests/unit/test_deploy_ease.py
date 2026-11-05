"""Deploying from a fresh checkout: a preflight that gates, hidden key entry, no local data shipped."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from paid_media_agent.admin import actions
from paid_media_agent.admin.envfile import read_env, write_env
from paid_media_agent.admin.processes import deploy_command
from paid_media_agent.cli import main
from paid_media_agent.deployment import local_data_files, stage_for_deploy
from tests.unit.test_admin_console import workspace  # noqa: F401 - shared fixture


def _project(root: Path) -> Path:
    for folder in ("workspace/analysis", "workspace/sources", "workspace/out", "config", ".git"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "workspace/analysis/.gitkeep").write_text("")
    (root / "workspace/analysis/art_1.json").write_text('{"rows": []}')
    (root / "workspace/sources/brief.md").write_text("private brief")
    (root / "workspace/out/report.html").write_text("<html></html>")
    (root / "workspace/skills/company-context").mkdir(parents=True)
    (root / "workspace/skills/company-context/SKILL.md").write_text("context")
    (root / "skills").symlink_to("workspace/skills")
    (root / "config/accounts.toml").write_text("[accounts]")
    (root / ".env").write_text("OPENAI_API_KEY=sk-secret")
    (root / ".git/HEAD").write_text("ref")
    (root / "agent.py").write_text("agent = None")
    return root


def test_local_working_data_is_listed_and_never_staged(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    assert [name for name, _ in local_data_files(root)] == [
        "workspace/analysis/art_1.json",
        "workspace/out/report.html",
        "workspace/sources/brief.md",
    ]
    staged = stage_for_deploy(root, tmp_path / "staged")
    shipped = {p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()}
    assert "workspace/sources/brief.md" not in shipped
    assert "workspace/analysis/art_1.json" not in shipped
    assert "workspace/out/report.html" not in shipped
    assert ".env" not in shipped and ".git/HEAD" not in shipped
    assert {
        "agent.py",
        "config/accounts.toml",
        "workspace/skills/company-context/SKILL.md",
        "workspace/analysis/.gitkeep",
    } <= shipped
    assert (staged / "skills").is_symlink() and (staged / "skills/company-context").is_dir()


def test_deploy_reads_and_saves_the_projects_own_env(tmp_path: Path) -> None:
    root = _project(tmp_path / "project")
    command = deploy_command(root, tmp_path / "staged")
    assert command[-3:] == (str(tmp_path / "staged"), "--env-file", str(root / ".env"))
    (root / ".env").unlink()
    assert "--env-file" not in deploy_command(root, tmp_path / "staged")


def test_preflight_names_what_to_set_and_warns_before_a_surprising_deploy(
    workspace: Path,  # noqa: F811
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("LANGSMITH_API_KEY", "ANTHROPIC_API_KEY", "PIPEBOARD_API_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    shutil.copy(project_root / "identity.py", workspace / "identity.py")
    blocked = actions.mda_check(workspace)
    assert blocked.status == "fail"
    assert blocked.detail["blocked_by"] == ["set ANTHROPIC_API_KEY"]
    assert any("sign in with your browser" in w for w in blocked.detail["warnings"])

    (workspace / "workspace/sources").mkdir(parents=True)
    (workspace / "workspace/sources/brief.md").write_text("x" * 2048)
    write_env(
        workspace,
        {"LANGSMITH_API_KEY": "lsv2_sk_" + "a" * 32, "ANTHROPIC_API_KEY": "sk-ant-" + "b" * 32},
    )
    ready = actions.mda_check(workspace)
    assert ready.status == "warn", ready.detail["blocked_by"]
    warnings = " | ".join(ready.detail["warnings"])
    assert "service key" in warnings
    assert "synthetic demo data" in warnings
    assert "config/accounts.toml is missing" in warnings
    assert "workspace/sources/brief.md (2 KB)" in warnings

    write_env(workspace, {"X_ADS_CONSUMER_KEY": "k", "X_ADS_CONSUMER_SECRET": "s"})
    write_env(workspace, {"X_ADS_ACCESS_TOKEN": "t", "X_ADS_ACCESS_TOKEN_SECRET": "u"})
    mixed = " | ".join(actions.mda_check(workspace).detail["warnings"])
    assert "Only x_ads is connected" in mixed


def test_cli_preflight_exits_non_zero_while_blocked(
    workspace: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("paid_media_agent.cli.project_root", lambda: workspace)
    result = CliRunner().invoke(main, ["mda", "check"])
    assert result.exit_code == 1
    assert "BLOCKED  set ANTHROPIC_API_KEY" in result.output


def test_a_bare_key_is_typed_hidden_in_a_terminal_and_refused_elsewhere(
    workspace: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("paid_media_agent.cli.project_root", lambda: workspace)
    refused = CliRunner().invoke(main, ["config", "set", "ANTHROPIC_API_KEY"])
    assert refused.exit_code == 2 and "in your own terminal" in refused.output
    assert "ANTHROPIC_API_KEY" not in read_env(workspace)

    prompts: list[tuple[str, bool]] = []
    answers = iter(["sk-ant-typed-not-echoed", ""])

    def prompt(text: str, *, hide_input: bool, **_: object) -> str:
        prompts.append((text, hide_input))
        return next(answers)

    monkeypatch.setattr("paid_media_agent.cli._stdin_is_terminal", lambda: True)
    monkeypatch.setattr("click.prompt", prompt)
    typed = CliRunner().invoke(main, ["config", "set", "ANTHROPIC_API_KEY"])
    assert typed.exit_code == 0, typed.output
    assert prompts == [("ANTHROPIC_API_KEY (input hidden; Enter keeps the current value)", True)]
    assert read_env(workspace)["ANTHROPIC_API_KEY"] == "sk-ant-typed-not-echoed"
    assert "sk-ant-typed-not-echoed" not in typed.output
    kept = CliRunner().invoke(main, ["config", "set", "ANTHROPIC_API_KEY"])
    assert kept.exit_code == 0 and "ANTHROPIC_API_KEY unchanged" in kept.output
    assert read_env(workspace)["ANTHROPIC_API_KEY"] == "sk-ant-typed-not-echoed", (
        "Enter never wipes"
    )
    os.environ.pop("ANTHROPIC_API_KEY", None)


def test_the_deploy_wrapper_passes_a_name_for_a_separate_copy(
    workspace: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr("paid_media_agent.cli.project_root", lambda: workspace)
    monkeypatch.setattr(
        actions,
        "mda_check",
        lambda _root: actions.ActionResult(
            action="mda_check",
            ok=True,
            status="ok",
            summary="ok",
            detail={"langsmith_key_set": True},
        ),
    )
    monkeypatch.setattr("subprocess.call", lambda command, **_: calls.append(tuple(command)) or 0)
    result = CliRunner().invoke(main, ["mda", "deploy", "--yes", "--name", "paid-media-agent-test"])
    assert result.exit_code == 0, result.output
    assert calls[0][-2:] == ("--name", "paid-media-agent-test")
    assert "deploy" in calls[0] and "--env-file" not in calls[0], "no .env in the fixture"


def test_a_browser_sign_in_deploy_is_handed_to_a_terminal(
    workspace: Path,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []
    monkeypatch.setattr("paid_media_agent.cli.project_root", lambda: workspace)
    monkeypatch.setattr(
        actions,
        "mda_check",
        lambda _root: actions.ActionResult(
            action="mda_check",
            ok=True,
            status="warn",
            summary="ready",
            detail={"langsmith_key_set": False},
        ),
    )
    monkeypatch.setattr("subprocess.call", lambda *a, **_: calls.append(a) or 0)
    result = CliRunner().invoke(main, ["mda", "deploy", "--yes"])
    assert result.exit_code == 1 and "in your own terminal" in result.output
    assert not calls, "nothing is deployed"


def test_discover_add_maps_every_new_live_account_once(
    workspace: Path,  # noqa: F811
) -> None:
    row = {"platform": "google_ads", "currency": "USD", "timezone": "America/New_York"}
    discovered = actions.ActionResult(
        action="accounts_discover",
        ok=True,
        status="ok",
        summary="",
        detail={
            "source": "pipeboard",
            "accounts": [
                {**row, "provider_account_id": "111", "name": "Acme Search", "mapped_alias": ""},
                {**row, "provider_account_id": "222", "name": "Acme Search", "mapped_alias": ""},
                {**row, "provider_account_id": "333", "name": "Old", "mapped_alias": "kept"},
                {
                    "platform": "meta_ads",
                    "provider_account_id": "444",
                    "name": "No currency",
                    "currency": "",
                    "timezone": "UTC",
                    "mapped_alias": "",
                },
            ],
        },
    )
    result = actions.accounts_add_discovered(workspace, discovered)
    assert result.detail["added"] == ["google-acme-search", "google-acme-search-2"]
    assert result.detail["skipped"] == ["meta_ads No currency"]
    mapped = (workspace / "config/accounts.toml").read_text()
    assert "google-acme-search" in mapped and "111" in mapped and "fixture" not in mapped
    fixtures = actions.accounts_add_discovered(
        workspace, discovered.model_copy(update={"detail": {"source": "fixture", "accounts": []}})
    )
    assert fixtures.status == "warn" and "nothing mapped" in fixtures.summary


def test_the_readme_installer_parses_and_never_takes_a_key(project_root: Path) -> None:
    import subprocess

    script = project_root / "install.sh"
    subprocess.run(["bash", "-n", str(script)], check=True)  # noqa: S603, S607
    text = script.read_text()
    assert "config set LANGSMITH_API_KEY ANTHROPIC_API_KEY PIPEBOARD_API_TOKEN" in text
    assert "=sk-" not in text and "=lsv2" not in text, "keys are typed hidden, never inline"
    readme = (project_root / "README.md").read_text()
    assert "raw.githubusercontent.com/langchain-ai/paid-media-agent/main/install.sh" in readme
