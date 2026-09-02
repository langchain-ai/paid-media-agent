"""The localhost console: token and host checks, static page, and action endpoints."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paid_media_agent.admin.server import create_console_app

TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def workspace(tmp_path: Path, project_root: Path) -> Path:
    for name in ("instructions.md", ".env.example", "agent.py"):
        shutil.copy(project_root / name, tmp_path / name)
    for directory in ("skills", "config", "channels", "docs", "src"):
        if (project_root / directory).exists() and directory != "src":
            shutil.copytree(project_root / directory, tmp_path / directory)
    (tmp_path / "workspace").mkdir()
    return tmp_path


@pytest.fixture
def client(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name in (
        "ANTHROPIC_API_KEY",
        "PIPEBOARD_API_TOKEN",
        "SLACK_BOT_TOKEN",
        "LANGSMITH_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    app = create_console_app(workspace, token=TOKEN)
    return TestClient(app, base_url="http://127.0.0.1:8765")


def test_page_and_static_assets_are_served_with_csp(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200 and "Paid Media Agent" in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/static/../pyproject.toml").status_code in (404, 400)


def test_api_requires_token_and_local_host(client: TestClient) -> None:
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/status", headers={"X-Admin-Token": "wrong"}).status_code == 401
    foreign = client.get("/api/status", headers={"X-Admin-Token": TOKEN, "Host": "evil.example"})
    assert foreign.status_code == 403
    assert client.get("/", headers={"Host": "evil.example"}).status_code == 403


def test_status_routes_and_config_round_trip(client: TestClient, workspace: Path) -> None:
    headers = {"X-Admin-Token": TOKEN}
    data = client.get("/api/status", headers=headers).json()
    assert [r["id"] for r in data["routes"]] == [
        "local",
        "pipeboard",
        "slack",
        "mda",
        "self_hosted",
        "writes",
    ]
    assert {p["name"] for p in data["processes"]} == {"serve", "slack", "mda-dev", "mda-deploy"}
    posted = client.post(
        "/api/config",
        headers=headers,
        json={
            "updates": {"PAID_MEDIA_MODEL": "openai:gpt-5.5", "OPENAI_API_KEY": "sk-" + "z" * 24}
        },
    ).json()
    assert posted["ok"] is True
    config = client.get("/api/config", headers=headers).json()
    keys = {k["name"]: k for k in config["detail"]["keys"]}
    assert (
        keys["OPENAI_API_KEY"]["value"] == "••••••••"
        and keys["PAID_MEDIA_MODEL"]["value"] == "openai:gpt-5.5"
    )
    assert "z" * 24 not in config.__repr__()
    bad = client.post("/api/config", headers=headers, json={"updates": {"EVIL": "x"}}).json()
    assert bad["status"] == "fail"
    routes = {r["id"]: r for r in client.get("/api/status", headers=headers).json()["routes"]}
    assert {s["id"]: s["status"] for s in routes["local"]["steps"]}["model"] == "done"


def test_actions_accounts_policy_and_kill_switch(client: TestClient, workspace: Path) -> None:
    headers = {"X-Admin-Token": TOKEN}
    assert client.post("/api/actions/nope", headers=headers, json={}).status_code == 404
    discovered = client.post("/api/actions/accounts_discover", headers=headers, json={}).json()
    first = discovered["detail"]["accounts"][0]
    assert first["mapped_alias"], "fixture accounts arrive already mapped to the example aliases"
    added = client.post(
        "/api/accounts",
        headers=headers,
        json={
            "alias": "primary",
            "platform": first["platform"],
            "provider_account_id": first["provider_account_id"] + "-new",
            "currency": "USD",
            "timezone": "UTC",
        },
    ).json()
    assert added["ok"], added
    assert (workspace / "config" / "accounts.toml").exists()
    assert client.delete("/api/accounts/primary", headers=headers).json()["ok"]
    policy = client.post(
        "/api/actions/policy_validate", headers=headers, json={"live": False}
    ).json()
    assert policy["ok"] and len(policy["detail"]["admitted"]) == 6
    engaged = client.post("/api/kill-switch", headers=headers, json={"engaged": True}).json()
    assert engaged["ok"]
    banner = client.get("/api/status", headers=headers).json()["result"]["detail"]["writes"][
        "kill_switch_engaged"
    ]
    assert banner is True
    assert (
        client.post("/api/kill-switch", headers=headers, json={"engaged": False}).json()["status"]
        == "fail"
    )
    assert client.post(
        "/api/kill-switch", headers=headers, json={"engaged": False, "confirm": True}
    ).json()["ok"]
    generated = client.post("/api/actions/generate_secrets", headers=headers, json={}).json()
    assert generated["ok"] and generated["detail"]["api_token_show_once"].endswith(":operator")


def test_demo_runs_through_the_console(client: TestClient) -> None:
    headers = {"X-Admin-Token": TOKEN}
    result = client.post(
        "/api/actions/demo_run", headers=headers, json={"with_proposal": True}
    ).json()
    assert result["ok"], result["summary"]
    assert "Comparison window" in result["detail"]["answer"]
    assert result["detail"]["receipt"]["status"] == "verified"


def test_process_endpoints_guard_deploy(client: TestClient) -> None:
    headers = {"X-Admin-Token": TOKEN}
    assert (
        client.post(
            "/api/processes/mda-deploy/start", headers=headers, json={"confirm": False}
        ).status_code
        == 409
    )
    assert client.post("/api/processes/unknown/start", headers=headers, json={}).status_code == 409
    log = client.get("/api/processes/serve/log", headers=headers).json()
    assert log["name"] == "serve" and log["running"] is False
