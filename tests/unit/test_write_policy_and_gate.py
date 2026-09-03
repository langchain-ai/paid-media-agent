from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import ToolMessage
from langchain_core.tools import StructuredTool

from paid_media_agent.domain.common import RiskLevel
from paid_media_agent.tools.catalog import AuthorizedToolCatalog, StaticCatalogProvider
from paid_media_agent.tools.pipeboard import invoke_mcp_tool
from paid_media_agent.tools.providers import ProviderError
from paid_media_agent.tools.write_policy import (
    WriteOperation,
    WritePolicyFile,
    fixture_write_policy,
)
from paid_media_agent.tools.writes import WriteDenied, WriteGate, classify_risk


def test_policy_file_validates_against_catalog(
    project_root: Path, catalog: AuthorizedToolCatalog
) -> None:
    policy_file = WritePolicyFile.from_toml(project_root / "config" / "write-policy.example.toml")
    policy, issues = policy_file.validate_against(catalog)
    assert set(policy.admitted_names()) == set(fixture_write_policy().admitted_names())
    assert {(i.tool_name, i.reason) for i in issues} == {
        ("google_ads__update_campaign_bid", "not_admitted")
    }
    budget = policy.get("google_ads__update_campaign_budget")
    assert budget is not None and budget.validate_only_arg == "validate_only"


def test_policy_rows_fail_closed_on_schema_and_catalog_mismatch(
    tmp_path: Path, catalog: AuthorizedToolCatalog
) -> None:
    toml = """
[operations."google_ads__update_campaign_budget"]
admitted = true
readback_tool = "google_ads__get_campaign"
target_arg = "campaign_id"
editable_fields = ["daily_budget", "lifetime_budget"]
readback_fields = { daily_budget = "daily_budget", lifetime_budget = "lifetime_budget" }

[operations."google_ads__mutate"]
admitted = true
readback_tool = "google_ads__get_campaign"
target_arg = "campaign_id"
editable_fields = ["operations"]
readback_fields = { operations = "operations" }

[operations."google_ads__list_campaigns"]
admitted = true
readback_tool = "google_ads__get_campaign"
target_arg = "status"
editable_fields = ["status"]
readback_fields = { status = "status" }

[operations."meta_ads__update_campaign_status"]
admitted = true
readback_tool = "meta_ads__update_campaign_budget"
target_arg = "campaign_id"
editable_fields = ["status"]
readback_fields = { status = "status" }
"""
    path = tmp_path / "policy.toml"
    path.write_text(toml)
    policy, issues = WritePolicyFile.from_toml(path).validate_against(catalog)
    assert policy.operations == ()
    reasons = {i.tool_name: i.reason for i in issues}
    assert reasons["google_ads__update_campaign_budget"].startswith(
        "schema_missing_fields:lifetime_budget"
    )
    assert reasons["google_ads__mutate"].startswith("catalog_class_denied")
    assert reasons["google_ads__list_campaigns"].startswith("catalog_class_read")
    assert reasons["meta_ads__update_campaign_status"] == "readback_tool_unavailable"


def test_unknown_policy_keys_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "policy.toml"
    path.write_text(
        '[operations."x__y"]\nadmitted = true\nreadback_tool = "r"\ntarget_arg = "t"\neditable_fields = ["f"]\nreadback_fields = { f = "f" }\nextra = 1\n'
    )
    with pytest.raises(ValueError):
        WritePolicyFile.from_toml(path)


def test_classify_risk_derives_reviewer_facts(catalog: AuthorizedToolCatalog) -> None:
    entry = catalog.get("google_ads__update_campaign_status")
    assert entry is not None
    op = fixture_write_policy().get("google_ads__update_campaign_status")
    assert op is not None
    flags = classify_risk(entry, op, {"status": "ENABLED"}, {"status": "PAUSED"})
    assert {"status_flip", "starts_delivery", "policy_high_risk"} <= set(flags)
    budget_entry = catalog.get("google_ads__update_campaign_budget")
    budget_op = fixture_write_policy().get("google_ads__update_campaign_budget")
    assert budget_entry is not None and budget_op is not None
    flags = classify_risk(budget_entry, budget_op, {"daily_budget": 500}, {"daily_budget": 300})
    assert {"budget_delta", "budget_increase"} <= set(flags) and "status_flip" not in flags
    flags = classify_risk(budget_entry, budget_op, {"daily_budget": 100}, {"daily_budget": 300})
    assert "budget_increase" not in flags and "budget_delta" in flags


def test_write_gate_matrix(tmp_path: Path) -> None:
    switch = tmp_path / "KILL_SWITCH"
    fake = WriteGate(writes_enabled=False, provider_is_fake=True, kill_switch_path=switch)
    fake.check("any")  # fakes pass without flags
    switch.write_text("incident")
    with pytest.raises(WriteDenied, match="kill_switch"):
        fake.check("any")
    switch.unlink()

    def live(**kwargs: object) -> WriteGate:
        base: dict[str, object] = {
            "writes_enabled": True,
            "provider_is_fake": False,
            "kill_switch_path": switch,
            "released_catalog_revision": "rev-1",
            "canary_tools": frozenset({"google_ads__update_campaign_budget"}),
            "current_revision": lambda: "rev-1",
        }
        base.update(kwargs)
        return WriteGate(**base)  # type: ignore[arg-type]

    live().check("google_ads__update_campaign_budget")
    with pytest.raises(WriteDenied, match="writes_disabled"):
        live(writes_enabled=False).check("google_ads__update_campaign_budget")
    with pytest.raises(WriteDenied, match="live_writes_not_released"):
        live(released_catalog_revision=None).check("google_ads__update_campaign_budget")
    with pytest.raises(WriteDenied, match="stale_catalog"):
        live(current_revision=lambda: "rev-2").check("google_ads__update_campaign_budget")
    with pytest.raises(WriteDenied, match="tool_not_released"):
        live().check("google_ads__update_campaign_status")
    assert "live provider" in live().describe() and "fake" in fake.describe()


async def test_invoke_mcp_tool_surfaces_errors_and_structured_content() -> None:
    async def ok(**kwargs: object) -> tuple[str, object]:
        return '{"campaign": {"id": "c1", "daily_budget": 5}}', None

    tool = StructuredTool(
        name="get_campaign",
        description="d",
        args_schema={"type": "object", "properties": {"campaign_id": {"type": "string"}}},
        coroutine=ok,
        response_format="content_and_artifact",
    )
    payload = await invoke_mcp_tool(tool, {"campaign_id": "c1"}, timeout=5)
    assert payload["campaign"]["daily_budget"] == 5

    async def failing(**kwargs: object) -> str:
        # Synthetic credential-shaped value built at runtime so the repository never carries one.
        raise RuntimeError("provider exploded with token " + "sk-ant-" + "a" * 30)

    bad = StructuredTool(
        name="bad",
        description="d",
        args_schema={"type": "object", "properties": {}},
        coroutine=failing,
        handle_tool_error=True,
    )
    with pytest.raises(ProviderError) as info:
        await invoke_mcp_tool(bad, {}, timeout=5)
    assert "sk-ant-" not in str(info.value)

    async def error_message(**kwargs: object) -> ToolMessage:
        return ToolMessage(
            content="isError from provider", tool_call_id="host-call", status="error"
        )

    err_tool = StructuredTool(
        name="err",
        description="d",
        args_schema={"type": "object", "properties": {}},
        coroutine=error_message,
    )
    with pytest.raises(ProviderError):
        await invoke_mcp_tool(err_tool, {}, timeout=5)


def test_operation_digest_changes_with_policy(catalog: AuthorizedToolCatalog) -> None:
    op = fixture_write_policy().get("google_ads__update_campaign_budget")
    assert op is not None
    changed = WriteOperation(**{**op.model_dump(), "risk": RiskLevel.HIGH})
    assert op.digest() != changed.digest()
    assert StaticCatalogProvider(catalog).current().revision
