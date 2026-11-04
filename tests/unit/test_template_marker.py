"""Every run names the template it came from, on MDA and locally, unless the operator turns it off."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from paid_media_agent.config import Settings, template_marker
from paid_media_agent.runtime.local import build_local_runtime
from paid_media_agent.testing.scripted_model import ScriptedChatModel


def mda_definition(
    project_root: Path, monkeypatch: pytest.MonkeyPatch, telemetry: str
) -> ModuleType:
    monkeypatch.delenv("PIPEBOARD_API_TOKEN", raising=False)
    # The import reads the developer's .env; pin what it needs so a local value cannot decide it.
    monkeypatch.setenv("PAID_MEDIA_MODEL", "anthropic:claude-sonnet-4-6")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    monkeypatch.setenv("PAID_MEDIA_TEMPLATE_TELEMETRY", telemetry)
    monkeypatch.chdir(project_root)
    sys.modules.pop("agent", None)
    return importlib.import_module("agent")


def test_the_marker_is_the_template_and_its_version_only() -> None:
    marker = template_marker()
    assert set(marker) == {"ls_template", "ls_template_version"}
    assert marker["ls_template"] == "langchain-ai/paid-media-agent"
    assert marker["ls_template_version"]


def test_the_mda_root_run_carries_the_marker_unless_turned_off(
    project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    on = mda_definition(project_root, monkeypatch, "true")
    assert on.agent.config["metadata"] == template_marker()
    off = mda_definition(project_root, monkeypatch, "false")
    assert "metadata" not in off.agent.config


@pytest.mark.parametrize("telemetry", [True, False])
def test_the_local_graph_carries_the_marker_unless_turned_off(
    settings: Settings, project_root: Path, telemetry: bool
) -> None:
    configured = settings.model_copy(update={"paid_media_template_telemetry": telemetry})
    runtime = build_local_runtime(
        configured, project_root=project_root, model=ScriptedChatModel(steps=[])
    )
    metadata = runtime.graph.config.get("metadata", {}) if runtime.graph.config else {}
    if telemetry:
        assert metadata["ls_template"] == "langchain-ai/paid-media-agent"
    else:
        assert "ls_template" not in metadata
