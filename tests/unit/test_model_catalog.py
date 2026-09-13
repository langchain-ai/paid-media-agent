"""The picker uses exact official IDs and never exposes provider credentials on failure."""

from functools import partial
from pathlib import Path

import httpx
import pytest

from paid_media_agent.admin import actions, envfile, model_catalog


def test_catalog_keeps_official_ids_and_follows_pagination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.url.host == "api.anthropic.com"
        assert request.headers["x-api-key"] == "catalog-test-key"
        if "after_id" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "data": [{"id": "new-model", "display_name": "New model"}],
                    "has_more": True,
                    "last_id": "new-model",
                },
            )
        assert request.url.params["after_id"] == "new-model"
        return httpx.Response(200, json={"data": [{"id": "older-model"}], "has_more": False})

    monkeypatch.setattr(
        model_catalog.httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(respond))
    )
    result = actions.models_list(tmp_path, "anthropic", api_key="catalog-test-key")
    assert result.ok
    assert result.detail["models"] == [
        {"id": "anthropic:new-model", "name": "New model", "provider": "anthropic"},
        {"id": "anthropic:older-model", "name": "older-model", "provider": "anthropic"},
    ]
    assert len(calls) == 2
    assert not (tmp_path / ".env").exists(), "Catalog lookup must not persist a draft key."


def test_catalog_failure_hides_provider_body_and_does_not_follow_redirects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(
            302, headers={"location": "https://other.example/models"}, text="catalog-test-key"
        )

    monkeypatch.setattr(
        model_catalog.httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(respond))
    )
    result = actions.models_list(tmp_path, "langsmith", api_key="catalog-test-key")
    assert not result.ok and not result.detail
    assert "catalog-test-key" not in result.model_dump_json()
    assert len(calls) == 1
    assert calls[0].url.host == "gateway.smith.langchain.com"


def test_catalog_requires_own_key_before_contacting_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-provider-key")

    def unexpected_request(*args, **kwargs):
        pytest.fail("Missing or unsupported provider keys must not make a network request.")

    monkeypatch.setattr(model_catalog.httpx, "Client", unexpected_request)
    assert not actions.models_list(tmp_path, "anthropic").ok
    assert not actions.models_list(tmp_path, "https://other.example").ok


def test_catalog_uses_runtime_credentials_and_forgets_cleared_exports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saved keys win, draft keys stay temporary, and clearing a key stops requests."""
    monkeypatch.setattr(envfile, "_EXPORTED_BY_CONSOLE", set())
    monkeypatch.setenv("ANTHROPIC_API_KEY", "shell-test-key")
    envfile.write_env(tmp_path, {"ANTHROPIC_API_KEY": "saved-test-key"})
    seen: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["x-api-key"])
        return httpx.Response(200, json={"data": [{"id": "test-model"}]})

    monkeypatch.setattr(
        model_catalog.httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(respond))
    )
    assert actions.models_list(tmp_path, "anthropic").ok
    assert actions.models_list(tmp_path, "anthropic", api_key="draft-test-key").ok
    assert actions.models_list(tmp_path, "anthropic").ok
    envfile.write_env(tmp_path, {"ANTHROPIC_API_KEY": ""})
    assert not actions.models_list(tmp_path, "anthropic").ok
    assert seen == ["saved-test-key", "draft-test-key", "saved-test-key"]
