"""Optional named local URLs must preserve console authentication and origin isolation."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from paid_media_agent.admin.server import _portless_url, create_console_app


def test_portless_accepts_only_the_configured_host_and_still_requires_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PORTLESS_URL", "https://paid-media.localhost")
    client = TestClient(
        create_console_app(tmp_path, token="local-test-token"),
        base_url="https://paid-media.localhost",
    )
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/api/config").status_code == 401
    headers = {"X-Admin-Token": "local-test-token"}
    assert client.get("/api/config", headers=headers).status_code == 200
    headers["Host"] = "other.localhost"
    assert client.get("/api/config", headers=headers).status_code == 403
    assert client.get("/", headers=headers).status_code == 403
    assert client.get("/static/app.js", headers=headers).status_code == 403


def test_portless_tokenless_mode_rejects_other_origins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origin = "http://paid-media.localhost:1355"
    monkeypatch.setenv("PORTLESS_URL", origin)
    client = TestClient(create_console_app(tmp_path, require_token=False), base_url=origin)
    assert client.get("/api/config", headers={"Origin": origin}).status_code == 200
    assert (
        client.get("/api/config", headers={"Origin": "http://other.localhost:1355"}).status_code
        == 403
    )
    assert client.get("/api/config", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    monkeypatch.setenv("PORTLESS_URL", "https://public.example.com")
    with pytest.raises(ValueError, match=".localhost origin"):
        create_console_app(tmp_path)
    monkeypatch.delenv("PORTLESS_URL")
    assert _portless_url() is None
    default = TestClient(create_console_app(tmp_path), base_url=origin)
    assert default.get("/").status_code == 403
