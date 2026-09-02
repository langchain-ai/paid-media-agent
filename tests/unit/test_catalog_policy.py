from __future__ import annotations

from paid_media_agent.domain.common import Platform
from paid_media_agent.tools.catalog import (
    DEFAULT_LOCAL_POLICY,
    RawTool,
    ToolClass,
    build_authorized_catalog,
    classify,
)
from paid_media_agent.tools.fixtures import FIXTURE_LOCAL_POLICY, build_fixture_catalog


def _raw(
    name: str,
    annotations: dict[str, object] | None,
    platform: str = "google_ads",
    schema: dict[str, object] | None = None,
) -> RawTool:
    return RawTool(
        platform=platform,
        name=name,
        description="d",
        input_schema=schema
        or {"type": "object", "properties": {"customer_id": {"type": "string"}}},
        annotations=annotations,
    )


def test_missing_metadata_is_denied_as_mutation() -> None:
    decision, _, _ = classify(_raw("get_things", None), DEFAULT_LOCAL_POLICY)
    assert (
        decision.tool_class is ToolClass.DENIED and decision.reason == "missing_mutation_metadata"
    )
    decision, _, _ = classify(_raw("get_things", {"readOnlyHint": "yes"}), DEFAULT_LOCAL_POLICY)
    assert decision.tool_class is ToolClass.DENIED


def test_raw_mutate_and_delete_are_denied_even_when_admitted() -> None:
    policy = FIXTURE_LOCAL_POLICY.model_copy(
        update={"admitted_mutations": ("google_ads__mutate", "google_ads__delete_campaign")}
    )
    for name in ("mutate", "delete_campaign", "remove_audience", "purge_all"):
        decision, _, _ = classify(_raw(name, {"readOnlyHint": False}), policy)
        assert decision.tool_class is ToolClass.DENIED, name


def test_unknown_platform_and_malformed_schema_fail_closed() -> None:
    decision, platform, _ = classify(
        _raw("list", {"readOnlyHint": True}, platform="tiktok_ads"), DEFAULT_LOCAL_POLICY
    )
    assert decision.tool_class is ToolClass.DENIED and platform is None
    decision, _, _ = classify(
        _raw("list", {"readOnlyHint": True}, schema={"type": "array"}), DEFAULT_LOCAL_POLICY
    )
    assert decision.reason == "malformed_schema"
    decision, _, _ = classify(
        _raw("list", {"readOnlyHint": True}, schema={"type": "object", "properties": {}}),
        DEFAULT_LOCAL_POLICY,
    )
    assert decision.reason == "no_account_scope"


def test_mutations_require_explicit_admission() -> None:
    decision, _, _ = classify(
        _raw("update_campaign_budget", {"readOnlyHint": False}), DEFAULT_LOCAL_POLICY
    )
    assert decision.reason == "mutation_not_admitted"
    decision, _, _ = classify(
        _raw("update_campaign_budget", {"readOnlyHint": False}), FIXTURE_LOCAL_POLICY
    )
    assert decision.tool_class is ToolClass.MUTATION
    decision, _, _ = classify(
        _raw("update_campaign_budget", {"readOnlyHint": False, "destructiveHint": True}),
        FIXTURE_LOCAL_POLICY,
    )
    assert decision.reason == "destructive_hint"


def test_fixture_catalog_shape_and_revision_stability() -> None:
    catalog = build_fixture_catalog()
    again = build_fixture_catalog()
    assert catalog.revision == again.revision
    read_names = {e.qualified_name for e in catalog.read_entries()}
    assert "google_ads__get_campaign_performance" in read_names
    assert all("mutate" not in n and "delete" not in n for n in read_names)
    denied_reasons = {
        e.name: e.policy.reason
        for e in catalog.denied_entries()
        if e.platform is Platform.GOOGLE_ADS
    }
    assert denied_reasons["mutate"] == "denied_name_policy"
    assert denied_reasons["delete_campaign"] == "denied_name_policy"
    assert denied_reasons["get_legacy_insights"] == "missing_mutation_metadata"
    assert len(catalog.mutation_entries()) == 6
    assert (
        catalog.search("campaign performance daily", platform=Platform.META_ADS)[0].name
        == "get_campaign_performance"
    )
    assert all(e.tool_class is ToolClass.READ for e in catalog.search("mutate delete budget"))


def test_revision_changes_when_a_schema_changes() -> None:
    tools = [_raw("list_campaigns", {"readOnlyHint": True})]
    first = build_authorized_catalog(tools, policy=DEFAULT_LOCAL_POLICY, source="t")
    changed = [
        _raw(
            "list_campaigns",
            {"readOnlyHint": True},
            schema={
                "type": "object",
                "properties": {"customer_id": {"type": "string"}, "limit": {"type": "integer"}},
            },
        )
    ]
    second = build_authorized_catalog(changed, policy=DEFAULT_LOCAL_POLICY, source="t")
    assert first.revision != second.revision
    assert first.entries[0].schema_hash != second.entries[0].schema_hash
