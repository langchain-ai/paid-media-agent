"""Fixture catalog and providers. No network, no credentials, synthetic data only."""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import date
from decimal import Decimal
from importlib import resources
from typing import Literal

from paid_media_agent.domain.common import PIPEBOARD_PLATFORMS, JsonValue, Platform
from paid_media_agent.tools.catalog import (
    DEFAULT_LOCAL_POLICY,
    AuthorizedToolCatalog,
    CatalogEntry,
    LocalPolicy,
    RawTool,
    build_authorized_catalog,
)
from paid_media_agent.tools.providers import ProviderError, ProviderResult, ProviderTimeout

FIXTURE_SOURCE = "fixture"
FIXTURE_ADMITTED_MUTATIONS = (
    "google_ads__update_campaign_budget",
    "google_ads__update_campaign_status",
    "meta_ads__update_campaign_budget",
    "meta_ads__update_campaign_status",
    "reddit_ads__update_campaign_budget",
    "reddit_ads__update_campaign_status",
)
FIXTURE_LOCAL_POLICY = LocalPolicy(
    platforms=DEFAULT_LOCAL_POLICY.platforms,
    denied_name_patterns=DEFAULT_LOCAL_POLICY.denied_name_patterns,
    admitted_mutations=FIXTURE_ADMITTED_MUTATIONS,
)

_ACCOUNT_ARG = {
    Platform.GOOGLE_ADS: "customer_id",
    Platform.META_ADS: "account_id",
    Platform.REDDIT_ADS: "account_id",
}


def _schema(
    account_arg: str, extra: dict[str, JsonValue], required: list[str]
) -> dict[str, JsonValue]:
    props: dict[str, JsonValue] = {
        account_arg: {"type": "string", "description": "Provider account id"}
    }
    props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": [account_arg, *required],
        "additionalProperties": False,
    }


def fixture_raw_tools() -> list[RawTool]:
    """A Pipeboard-shaped catalog including tools that policy must deny."""
    tools: list[RawTool] = []
    for platform in PIPEBOARD_PLATFORMS:
        account_arg = _ACCOUNT_ARG[platform]
        endpoint = f"fixture://{platform.value}"
        date_props: dict[str, JsonValue] = {
            "start_date": {"type": "string", "format": "date"},
            "end_date": {"type": "string", "format": "date"},
        }
        tools.extend(
            [
                RawTool(
                    platform=platform.value,
                    name="list_campaigns",
                    description="List campaigns with status and daily budget for an account.",
                    input_schema=_schema(account_arg, {"status": {"type": "string"}}, []),
                    annotations={"readOnlyHint": True, "destructiveHint": False},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="get_campaign_performance",
                    description=(
                        "Daily campaign performance rows (spend, impressions, clicks, conversions, "
                        "conversion value where reported) for an inclusive date range."
                    ),
                    input_schema=_schema(account_arg, date_props, ["start_date", "end_date"]),
                    annotations={"readOnlyHint": True, "destructiveHint": False},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="get_ad_group_performance",
                    description=(
                        "Daily ad group performance rows (spend, impressions, clicks, conversions, "
                        "conversion value where reported) with the parent campaign id, for an "
                        "inclusive date range."
                    ),
                    input_schema=_schema(account_arg, date_props, ["start_date", "end_date"]),
                    annotations={"readOnlyHint": True, "destructiveHint": False},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="get_campaign",
                    description="Current configuration of one campaign: status and daily budget.",
                    input_schema=_schema(
                        account_arg, {"campaign_id": {"type": "string"}}, ["campaign_id"]
                    ),
                    annotations={"readOnlyHint": True, "destructiveHint": False},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="update_campaign_budget",
                    description="Set a campaign daily budget in account currency.",
                    input_schema=_schema(
                        account_arg,
                        {
                            "campaign_id": {"type": "string"},
                            "daily_budget": {"type": "number", "minimum": 0},
                            "validate_only": {"type": "boolean"},
                        },
                        ["campaign_id", "daily_budget"],
                    ),
                    annotations={
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                    },
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="update_campaign_status",
                    description="Pause or enable a campaign.",
                    input_schema=_schema(
                        account_arg,
                        {
                            "campaign_id": {"type": "string"},
                            "status": {"type": "string", "enum": ["ENABLED", "PAUSED", "ACTIVE"]},
                        },
                        ["campaign_id", "status"],
                    ),
                    annotations={
                        "readOnlyHint": False,
                        "destructiveHint": False,
                        "idempotentHint": True,
                    },
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="delete_campaign",
                    description="Permanently delete a campaign.",
                    input_schema=_schema(
                        account_arg, {"campaign_id": {"type": "string"}}, ["campaign_id"]
                    ),
                    annotations={"readOnlyHint": False, "destructiveHint": True},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="mutate",
                    description="Raw mutate endpoint accepting arbitrary operations.",
                    input_schema=_schema(
                        account_arg, {"operations": {"type": "array"}}, ["operations"]
                    ),
                    annotations={"readOnlyHint": False, "destructiveHint": False},
                    source_endpoint=endpoint,
                ),
                RawTool(
                    platform=platform.value,
                    name="get_legacy_insights",
                    description="Legacy insights endpoint without MCP annotations.",
                    input_schema=_schema(account_arg, date_props, []),
                    annotations=None,
                    source_endpoint=endpoint,
                ),
            ]
        )
    return tools


def build_fixture_catalog(policy: LocalPolicy = FIXTURE_LOCAL_POLICY) -> AuthorizedToolCatalog:
    return build_authorized_catalog(fixture_raw_tools(), policy=policy, source=FIXTURE_SOURCE)


def load_fixture_dataset(platform: Platform) -> dict[str, JsonValue]:
    text = (
        resources.files("paid_media_agent.fixtures.data")
        .joinpath(f"{platform.value}.json")
        .read_text("utf-8")
    )
    data: dict[str, JsonValue] = json.loads(text)
    return data


class FixtureState:
    """Mutable in-memory copy of the fixture datasets shared by the read and write fakes."""

    def __init__(self) -> None:
        self.datasets: dict[Platform, dict[str, JsonValue]] = {
            platform: copy.deepcopy(load_fixture_dataset(platform))
            for platform in PIPEBOARD_PLATFORMS
        }

    def account_id(self, platform: Platform) -> str:
        return str(self.datasets[platform]["account_id"])

    def campaign(self, platform: Platform, campaign_id: str) -> dict[str, JsonValue] | None:
        campaigns = self.datasets[platform]["campaigns"]
        for campaign in campaigns:
            if isinstance(campaign, dict) and campaign.get("id") == campaign_id:
                return campaign
        return None


AD_GROUP_SHARES: tuple[tuple[str, Decimal], ...] = (("a", Decimal("0.6")), ("b", Decimal("0.4")))
"""Each fixture campaign is split into two ad groups with fixed shares, so ad-group rows
reconcile to their campaign exactly and the demo shows one grain below campaign."""


def ad_group_rows(rows: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    """Derive daily ad-group rows from campaign rows; the last share takes the rounding remainder."""
    derived: list[dict[str, JsonValue]] = []
    for row in rows:
        remaining = {
            k: Decimal(str(row[k])) for k in ("spend", "impressions", "clicks", "conversions")
        }
        if row.get("value") is not None:
            remaining["value"] = Decimal(str(row["value"]))
        for index, (suffix, share) in enumerate(AD_GROUP_SHARES):
            last = index == len(AD_GROUP_SHARES) - 1
            part: dict[str, JsonValue] = {
                "date": row["date"],
                "campaign_id": row["campaign_id"],
                "ad_group_id": f"{row['campaign_id']}-{suffix}",
            }
            for key, total in list(remaining.items()):
                whole = key in ("impressions", "clicks")
                value = (
                    total
                    if last
                    else (total * share).quantize(Decimal(1) if whole else Decimal("0.01"))
                )
                remaining[key] = total - value
                part[key] = int(value) if whole else str(value)
            derived.append(part)
    return derived


def _to_native_rows(
    platform: Platform, rows: list[dict[str, JsonValue]]
) -> list[dict[str, JsonValue]]:
    """Shape rows the way each platform reports them so normalization is exercised honestly."""
    native: list[dict[str, JsonValue]] = []
    for row in rows:
        spend = Decimal(str(row["spend"]))
        if platform is Platform.GOOGLE_ADS:
            item: dict[str, JsonValue] = {
                "date": row["date"],
                "campaign_id": row["campaign_id"],
                **({"ad_group_id": row["ad_group_id"]} if "ad_group_id" in row else {}),
                "cost_micros": int(spend * 1_000_000),
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "conversions": row["conversions"],
                "conversions_value": row.get("value"),
            }
        elif platform is Platform.META_ADS:
            item = {
                "date_start": row["date"],
                "campaign_id": row["campaign_id"],
                **({"adset_id": row["ad_group_id"]} if "ad_group_id" in row else {}),
                "spend": str(spend),
                "impressions": row["impressions"],
                "link_clicks": row["clicks"],
                "purchases": row["conversions"],
                "purchase_value": row.get("value"),
                "attribution": "7d_click_1d_view",
            }
        else:
            item = {
                "date": row["date"],
                "campaign_id": row["campaign_id"],
                **({"ad_group_id": row["ad_group_id"]} if "ad_group_id" in row else {}),
                "spend_micros": int(spend * 1_000_000),
                "impressions": row["impressions"],
                "clicks": row["clicks"],
                "conversions": row["conversions"],
            }
            if "value" in row:
                item["conversion_value"] = row["value"]
        native.append(item)
    return native


class FixtureReadProvider:
    """Serves fixture reads. Account ids must match the dataset, like a real provider."""

    def __init__(self, state: FixtureState | None = None) -> None:
        self.state = state or FixtureState()
        self.calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.fail_reads: dict[str, int] = {}
        """Tool name -> number of upcoming calls that time out. Tests use it to bound readback."""

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        self.calls.append((entry.qualified_name, dict(arguments)))
        remaining = self.fail_reads.get(entry.qualified_name, 0)
        if remaining > 0:
            self.fail_reads[entry.qualified_name] = remaining - 1
            raise ProviderTimeout("provider read timed out")
        dataset = self.state.datasets[entry.platform]
        account_arg = entry.account_arg or ""
        if arguments.get(account_arg) != dataset["account_id"]:
            raise ProviderError("account not found or not permitted")
        campaigns = dataset["campaigns"]
        meta = {
            "currency": str(dataset["currency"]),
            "timezone": str(dataset["timezone"]),
            "data_complete_through": str(dataset["data_complete_through"]),
        }
        if entry.name == "list_campaigns":
            status = arguments.get("status")
            rows = [c for c in campaigns if status is None or c["status"] == status]
            return ProviderResult(payload={"campaigns": rows}, **meta)
        if entry.name == "get_campaign":
            campaign = self.state.campaign(entry.platform, str(arguments.get("campaign_id")))
            if campaign is None:
                raise ProviderError("campaign not found in this account")
            return ProviderResult(payload={"campaign": dict(campaign)}, **meta)
        if entry.name in ("get_campaign_performance", "get_ad_group_performance"):
            start = date.fromisoformat(str(arguments["start_date"]))
            end = date.fromisoformat(str(arguments["end_date"]))
            selected = [
                r for r in dataset["daily"] if start <= date.fromisoformat(str(r["date"])) <= end
            ]
            grain = "campaign"
            if entry.name == "get_ad_group_performance":
                selected, grain = ad_group_rows(selected), "ad_group"
            totals = {
                "spend": str(sum(Decimal(str(r["spend"])) for r in selected)),
                "clicks": sum(int(r["clicks"]) for r in selected),
                "impressions": sum(int(r["impressions"]) for r in selected),
                "row_count": len(selected),
            }
            names = {c["id"]: c["name"] for c in campaigns}
            if grain == "ad_group":
                names = {
                    f"{cid}-{suffix}": f"{name} / ad group {suffix.upper()}"
                    for cid, name in names.items()
                    for suffix, _ in AD_GROUP_SHARES
                }
            covered = sorted(str(r["date"]) for r in dataset["daily"])
            return ProviderResult(
                payload={
                    "rows": _to_native_rows(entry.platform, selected),
                    "entity_type": grain,
                    "entity_names": names,
                    "totals": totals,
                    # Fixture data is static; say what it covers so an empty window is explained.
                    "fixture_data_window": {"start": covered[0], "end": covered[-1]}
                    if covered
                    else None,
                },
                **meta,
            )
        raise ProviderError("fixture read tool not implemented")


FakeWriteBehavior = Literal[
    "succeed",
    "timeout_after_commit",
    "timeout_without_commit",
    "error",
    "silent_no_change",
    "validation_error",
]


class FakeWriteProvider:
    """Constructor-injected mutation fake. It is the only write path automated tests can reach."""

    def __init__(self, state: FixtureState, behavior: FakeWriteBehavior = "succeed") -> None:
        self.state = state
        self.behavior = behavior
        self.mutation_calls: list[tuple[str, dict[str, JsonValue]]] = []
        self.validation_calls: list[tuple[str, dict[str, JsonValue]]] = []

    def _apply(self, entry: CatalogEntry, arguments: dict[str, JsonValue]) -> dict[str, JsonValue]:
        campaign = self.state.campaign(entry.platform, str(arguments.get("campaign_id")))
        if campaign is None:
            raise ProviderError("campaign not found in this account")
        if entry.name == "update_campaign_budget":
            campaign["daily_budget"] = float(Decimal(str(arguments["daily_budget"])))
        elif entry.name == "update_campaign_status":
            campaign["status"] = str(arguments["status"])
        else:
            raise ProviderError("fixture mutation not implemented")
        return {
            "operation_ref": f"fixture-op-{len(self.mutation_calls)}",
            "campaign": dict(campaign),
        }

    async def call_mutation(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> dict[str, JsonValue]:
        self.mutation_calls.append((entry.qualified_name, dict(arguments)))
        dataset = self.state.datasets[entry.platform]
        if arguments.get(entry.account_arg or "") != dataset["account_id"]:
            raise ProviderError("account not found or not permitted")
        if arguments.get("validate_only") is True:
            # Provider-side validation: no state change, no operation reference.
            self.mutation_calls.pop()
            self.validation_calls.append((entry.qualified_name, dict(arguments)))
            if (
                self.behavior == "validation_error"
                or self.state.campaign(entry.platform, str(arguments.get("campaign_id"))) is None
            ):
                raise ProviderError("validation rejected the payload")
            return {"validated": True}
        if self.behavior == "validation_error":
            raise ProviderError("validation rejected the payload")
        if self.behavior == "error":
            raise ProviderError("provider rejected the mutation")
        if self.behavior == "timeout_without_commit":
            raise ProviderTimeout("provider timed out")
        if self.behavior == "silent_no_change":
            return {"operation_ref": "fixture-op-noop"}
        result = self._apply(entry, arguments)
        if self.behavior == "timeout_after_commit":
            raise ProviderTimeout("provider timed out")
        await asyncio.sleep(0)
        return result
