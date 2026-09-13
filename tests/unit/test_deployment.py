"""Saved customization must reach the SDK declarations and survive a real MDA build."""

from __future__ import annotations

import runpy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from paid_media_agent.admin import actions
from paid_media_agent.admin.actions import config_set
from paid_media_agent.admin.envfile import read_env
from paid_media_agent.deployment import DeploymentSettings


def test_customization_reaches_channels_and_compiled_schedules(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for directory in ("channels", "schedules"):
        shutil.copytree(project_root / directory, tmp_path / directory)
    shutil.copyfile(project_root / "identity.py", tmp_path / "identity.py")
    (tmp_path / ".gitignore").write_text("channels/slack-icon.png\n")
    Image.new("RGB", (512, 512), "#123456").save(tmp_path / "channels/slack-icon.png")
    (tmp_path / "instructions.md").write_text("Config test")
    (tmp_path / "agent.py").write_text(
        'from managed_deepagents import define_deep_agent\nagent = define_deep_agent(name="config-test", model="anthropic:claude-sonnet-4-6")\n'
    )
    weekly = tmp_path / "schedules/weekly_report.py"
    before_prompt = runpy.run_path(str(weekly))["schedule"].config["prompt"]
    updates = {
        "PAID_MEDIA_SLACK_NAME": "Campaign Analyst",
        "PAID_MEDIA_SLACK_DESCRIPTION": "Tracks campaign spend and conversions.",
        "PAID_MEDIA_SLACK_BACKGROUND_COLOR": "#123456",
        "PAID_MEDIA_SLACK_TRIGGER_ON_ALL_MESSAGES": "true",
        "PAID_MEDIA_SLACK_ALLOW_BOT_TRIGGERS": "true",
        "PAID_MEDIA_REPORT_TIME": "09:30",
        "PAID_MEDIA_REPORT_TIMEZONE": "America/Los_Angeles",
        "PAID_MEDIA_WEEKLY_REPORT_DAY": "2",
        "PAID_MEDIA_MONTHLY_REPORT_DAY": "5",
    }
    for name in updates:
        monkeypatch.delenv(name, raising=False)
    result = config_set(tmp_path, updates)
    assert result.ok, result.summary
    monkeypatch.chdir(tmp_path)
    channel = runpy.run_path(str(tmp_path / "channels/slack.py"))["channel"]
    provider = channel.requirements("slack")["providerConfig"]
    assert provider["app"]["name"] == "Campaign Analyst"
    assert provider["app"]["icon"] == "slack-icon.png"
    assert provider["app"]["backgroundColor"] == "#123456"
    assert provider["triggerOnAllMessages"] and provider["allowBotTriggers"]
    assert runpy.run_path(str(weekly))["schedule"].config["prompt"] == before_prompt
    assert runpy.run_path(str(weekly))["schedule"].config["cron"] == "30 9 * * WED"
    assert (
        runpy.run_path(str(tmp_path / "schedules/monthly_report.py"))["schedule"].config["cron"]
        == "30 9 5 * *"
    )
    # The CLI's static compiler rejects computed schedule values even when imports work.
    build = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "managed_deepagents", "build", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert build.returncode == 0, build.stderr
    compiled = tmp_path / ".mda/build"
    assert (compiled / "channels/slack-icon.png").is_file()
    assert (
        runpy.run_path(str(compiled / "schedules/weekly_report.py"))["schedule"].config["timezone"]
        == "America/Los_Angeles"
    )

    monkeypatch.setattr(actions, "_agent_import_smoke", lambda _: "ok")
    assert actions.mda_check(tmp_path).detail["report_schedules"] == "ok"
    env_file = tmp_path / ".env"
    env_file.write_text(env_file.read_text().replace("09:30", "10:30"))
    assert "out of sync" in str(actions.mda_check(tmp_path).detail["report_schedules"])


def test_invalid_customization_does_not_change_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in DeploymentSettings.model_fields:
        monkeypatch.delenv(f"PAID_MEDIA_{name.upper()}", raising=False)
    (tmp_path / ".env").write_text('PAID_MEDIA_SLACK_NAME="Existing Agent"\n')
    before = (tmp_path / ".env").read_bytes()
    for updates in (
        {"PAID_MEDIA_SLACK_NAME": "-invalid"},
        {"PAID_MEDIA_SLACK_BACKGROUND_COLOR": "red"},
        {"PAID_MEDIA_REPORT_TIMEZONE": "Not/AZone"},
        {"PAID_MEDIA_MONTHLY_REPORT_DAY": "31"},
        {"PAID_MEDIA_WEEKLY_REPORT_DAY": "7"},
        {"PAID_MEDIA_REPORT_TIME": "09:30:30"},
    ):
        result = config_set(tmp_path, updates)
        assert not result.ok
        assert (tmp_path / ".env").read_bytes() == before
    assert config_set(tmp_path, {"PAID_MEDIA_REPORT_TIME": "09:00"}).ok
    assert not (tmp_path / "schedules").exists()
    assert read_env(tmp_path)["PAID_MEDIA_SLACK_NAME"] == "Existing Agent"


def test_compose_slack_shares_runtime_config_and_storage(project_root: Path) -> None:
    import yaml

    services = yaml.safe_load((project_root / "docker-compose.yml").read_text())["services"]
    api, slack = services["api"], services["slack"]
    assert api["ports"] == ["127.0.0.1:8080:8080"]
    assert slack["profiles"] == ["slack"]
    assert slack["command"] == ["paid-media-agent", "slack"]
    assert slack["environment"] == api["environment"]
    assert slack["volumes"] == api["volumes"]
    assert {
        "workspace:/app/workspace",
        "./workspace/skills:/app/skills:ro",
        "./config:/app/config:ro",
    } <= set(slack["volumes"])
    assert slack["healthcheck"] == {"disable": True}


def test_removed_schedule_stays_disabled_when_updating_settings(
    tmp_path: Path, project_root: Path
) -> None:
    shutil.copytree(project_root / "schedules", tmp_path / "schedules")
    (tmp_path / "schedules/weekly_report.py").unlink()
    result = config_set(tmp_path, {"PAID_MEDIA_REPORT_TIME": "09:30"})
    assert result.ok, result.summary
    assert not (tmp_path / "schedules/weekly_report.py").exists()
    assert (
        runpy.run_path(str(tmp_path / "schedules/monthly_report.py"))["schedule"].config["cron"]
        == "30 9 1 * *"
    )
