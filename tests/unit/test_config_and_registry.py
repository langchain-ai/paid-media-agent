from __future__ import annotations

from pathlib import Path

import pytest

from paid_media_agent.config import AccountRegistry, ModelConfig, Settings
from paid_media_agent.middleware.tool_selection import (
    SelectionStrategy,
    build_selection_middleware,
    capabilities_for,
    plan_selection,
)


def test_model_config_requires_provider_prefix() -> None:
    with pytest.raises(ValueError):
        ModelConfig.parse("claude-sonnet-4-6")
    config = ModelConfig.parse("Anthropic:claude-sonnet-4-6", base_url="https://proxy.example/v1")
    assert config.provider == "anthropic"
    assert config.spec == "anthropic:claude-sonnet-4-6"
    assert str(config.base_url).startswith("https://proxy.example")


def test_registry_is_exact_not_substring() -> None:
    assert capabilities_for(ModelConfig.parse("anthropic:claude-sonnet-4-6")).native_tool_search
    unknown = capabilities_for(ModelConfig.parse("anthropic:claude-sonnet-4-6-experimental"))
    assert not unknown.native_tool_search and not unknown.verified
    assert not capabilities_for(ModelConfig.parse("openai:gpt-4o")).native_tool_search


def test_plan_selection_paths() -> None:
    native = plan_selection(ModelConfig.parse("openai:gpt-5.5"), max_tools=6)
    assert native.strategy is SelectionStrategy.PROVIDER_NATIVE
    proxied = plan_selection(
        ModelConfig.parse("openai:gpt-5.5", base_url="https://proxy.example/v1"), max_tools=6
    )
    assert proxied.strategy is SelectionStrategy.PORTABLE_SELECTOR
    google = plan_selection(ModelConfig.parse("google_genai:gemini-3-flash"), max_tools=6)
    assert google.strategy is SelectionStrategy.PORTABLE_SELECTOR
    scripted = plan_selection(ModelConfig.parse("scripted:demo"), max_tools=6)
    assert scripted.strategy is SelectionStrategy.NONE
    assert (
        build_selection_middleware(scripted, searchable_tool_names=["a"], always_include=["b"])
        == ()
    )


def test_settings_secret_helpers_never_expose_values(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        paid_media_api_tokens="tok-abc:alice,tok-def:bob,malformed",
        paid_media_approver_ids="alice, bob",
        pipeboard_api_token="",
    )
    assert settings.api_token_map() == {"tok-abc": "alice", "tok-def": "bob"}
    assert settings.approver_refs() == frozenset({"alice", "bob"})
    assert settings.pipeboard_api_token is None
    assert "tok-abc" not in repr(settings)


def test_account_registry_from_toml(project_root: Path) -> None:
    registry = AccountRegistry.from_toml(project_root / "config" / "accounts.example.toml")
    assert registry.aliases() == ("demo-google", "demo-meta", "demo-reddit")
    binding = registry.resolve("demo-google")
    assert binding is not None and binding.platform.value == "google_ads"
    assert registry.resolve("unknown") is None
    assert "fixture-google-0001" in registry.provider_ids()
