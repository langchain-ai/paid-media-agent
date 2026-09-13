"""Direct LinkedIn, X, and OpenAI Ads adapters: request shape, auth, and normalization."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import Platform
from paid_media_agent.tools.catalog import build_authorized_catalog
from paid_media_agent.tools.direct import (
    CompositeReadProvider,
    configured_direct_platforms,
    direct_raw_tools,
    direct_read_providers,
)
from paid_media_agent.tools.direct.linkedin import LinkedInReadProvider, linkedin_raw_tools
from paid_media_agent.tools.direct.openai_ads import OpenAIAdsReadProvider, openai_ads_raw_tools
from paid_media_agent.tools.direct.x_ads import (
    XAdsReadProvider,
    oauth1_header,
    stats_windows,
    x_ads_raw_tools,
)
from paid_media_agent.tools.normalize import normalize_rows
from paid_media_agent.tools.providers import ProviderError


def _factory(handler: Any) -> Any:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _catalog() -> Any:
    return build_authorized_catalog(
        [*linkedin_raw_tools(), *x_ads_raw_tools(), *openai_ads_raw_tools()], source="direct"
    )


def test_direct_tools_classify_as_reads_with_account_scope() -> None:
    catalog = _catalog()
    names = {e.qualified_name: e for e in catalog.read_entries()}
    assert (
        "linkedin_ads__get_campaign_performance" in names
        and "x_ads__get_campaign_performance" in names
    )
    assert "openai_ads__list_campaigns" in names
    denied = {e.qualified_name: e.policy.reason for e in catalog.denied_entries()}
    assert denied["linkedin_ads__list_ad_accounts"] == "no_account_scope", (
        "account listing is host-only"
    )


def test_settings_direct_platforms_require_complete_credentials(tmp_path: Any) -> None:
    settings = Settings(_env_file=None, linkedin_access_token="tok", x_ads_consumer_key="k")  # type: ignore[call-arg]
    assert configured_direct_platforms(settings) == (Platform.LINKEDIN_ADS,)
    assert {t.platform for t in direct_raw_tools(settings)} == {"linkedin_ads"}


def test_pipeboard_linkedin_takes_precedence_over_saved_direct_credentials() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        pipeboard_api_token="pipeboard-test-token",
        linkedin_access_token="legacy-direct-token",
    )
    assert (
        settings.pipeboard_endpoints()[Platform.LINKEDIN_ADS]
        == "https://linkedin-ads.mcp.pipeboard.co/"
    )
    assert Platform.LINKEDIN_ADS not in configured_direct_platforms(settings)
    assert not any(tool.platform == "linkedin_ads" for tool in direct_raw_tools(settings))
    assert Platform.LINKEDIN_ADS not in direct_read_providers(settings)


async def test_linkedin_daily_analytics_request_and_refresh_on_401() -> None:
    seen: list[httpx.Request] = []
    state = {"token": "old-token"}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.host == "www.linkedin.com":
            return httpx.Response(200, json={"access_token": "new-token", "expires_in": 100})
        if request.headers["Authorization"] != "Bearer new-token" and state["token"] == "old-token":
            state["token"] = "expired"
            return httpx.Response(401, json={"message": "expired"})
        if request.url.path == "/rest/adAnalytics":
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "dateRange": {"start": {"year": 2026, "month": 8, "day": 1}},
                            "pivotValues": ["urn:li:sponsoredCampaign:77"],
                            "impressions": 1000,
                            "clicks": 20,
                            "costInLocalCurrency": "42.5",
                            "externalWebsiteConversions": 3,
                        },
                    ]
                },
            )
        if request.url.path.endswith("/adCampaigns"):
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "id": 77,
                            "name": "Brand",
                            "status": "ACTIVE",
                            "dailyBudget": {"amount": "50", "currencyCode": "USD"},
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = LinkedInReadProvider(
        access_token=SecretStr("old-token"),
        refresh_token=SecretStr("r"),
        client_id="cid",
        client_secret=SecretStr("cs"),
        client_factory=_factory(handler),
    )
    entry = _catalog().get("linkedin_ads__get_campaign_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "123", "start_date": "2026-08-01", "end_date": "2026-08-14"}
    )
    analytics = next(
        r
        for r in seen
        if r.url.path == "/rest/adAnalytics" and r.headers["Authorization"] == "Bearer new-token"
    )
    assert (
        analytics.headers["LinkedIn-Version"]
        and analytics.headers["X-Restli-Protocol-Version"] == "2.0.0"
    )
    assert "dateRange=(start:(year:2026,month:8,day:1),end:(year:2026,month:8,day:14))" in str(
        analytics.url
    )
    assert "pivot=CAMPAIGN&timeGranularity=DAILY" in str(analytics.url)
    row = result.payload["rows"][0]
    assert row == {
        "date": "2026-08-01",
        "campaign_id": "77",
        "campaign_name": "Brand",
        "spend": "42.5",
        "impressions": 1000,
        "clicks": 20,
        "conversions": 3,
    }
    normalized, missing = normalize_rows(
        platform=Platform.LINKEDIN_ADS,
        account_ref="li",
        currency="USD",
        timezone="UTC",
        rows=result.payload["rows"],
        entity_type=__import__(
            "paid_media_agent.domain.common", fromlist=["EntityType"]
        ).EntityType.CAMPAIGN,
        data_complete_through=None,
    )
    assert str(normalized[0].spend) == "42.500000" and missing == ("conversion_value",)
    with pytest.raises(ProviderError):
        await provider.call_read(
            entry, {"account_id": "12; drop", "start_date": "2026-08-01", "end_date": "2026-08-14"}
        )


def test_oauth1_header_is_deterministic_and_percent_encoded() -> None:
    header = oauth1_header(
        "GET",
        "https://ads-api.x.com/12/accounts",
        {"count": "200"},
        consumer_key="ck",
        consumer_secret="cs",
        token="tk",
        token_secret="ts",
        nonce="abc",
        timestamp="1700000000",
    )
    assert header.startswith("OAuth ") and 'oauth_signature_method="HMAC-SHA1"' in header
    assert 'oauth_consumer_key="ck"' in header and 'oauth_nonce="abc"' in header
    again = oauth1_header(
        "GET",
        "https://ads-api.x.com/12/accounts",
        {"count": "200"},
        consumer_key="ck",
        consumer_secret="cs",
        token="tk",
        token_secret="ts",
        nonce="abc",
        timestamp="1700000000",
    )
    assert header == again


def test_stats_windows_slice_seven_days_utc() -> None:
    from datetime import date

    windows = stats_windows(date(2026, 8, 1), date(2026, 8, 16))
    assert windows[0] == ("2026-08-01T00:00:00Z", "2026-08-08T00:00:00Z")
    assert windows[-1] == ("2026-08-15T00:00:00Z", "2026-08-17T00:00:00Z") and len(windows) == 3


async def test_x_ads_daily_stats_chunk_ids_and_map_micros() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["Authorization"].startswith("OAuth ")
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": f"c{i}",
                            "name": f"Camp {i}",
                            "entity_status": "ACTIVE",
                            "daily_budget_amount_local_micro": 5_000_000,
                            "currency": "USD",
                        }
                        for i in range(25)
                    ],
                    "next_cursor": None,
                },
            )
        if "/stats/accounts/" in request.url.path:
            ids = request.url.params["entity_ids"].split(",")
            assert len(ids) <= 20 and request.url.params["granularity"] == "DAY"
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": cid,
                            "id_data": [
                                {
                                    "metrics": {
                                        "impressions": [10, 20],
                                        "clicks": [1, 2],
                                        "billed_charge_local_micro": [1_500_000, 2_500_000],
                                        "conversion_purchases": {"metric": [0, 1]},
                                    }
                                }
                            ],
                        }
                        for cid in ids
                    ]
                },
            )
        return httpx.Response(404)

    provider = XAdsReadProvider(
        consumer_key="ck",
        consumer_secret=SecretStr("cs"),
        access_token=SecretStr("tk"),
        access_token_secret=SecretStr("ts"),
        client_factory=_factory(handler),
    )
    entry = _catalog().get("x_ads__get_campaign_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "18ce54", "start_date": "2026-08-01", "end_date": "2026-08-02"}
    )
    stats_calls = [r for r in seen if "/stats/" in r.url.path]
    assert len(stats_calls) == 2, "25 ids -> two chunks of at most 20 for one 2-day window"
    rows = result.payload["rows"]
    assert len(rows) == 50 and rows[0]["date"] == "2026-08-01" and rows[1]["date"] == "2026-08-02"
    assert rows[1]["spend_micros"] == 2_500_000 and rows[1]["conversions"] == 1.0


async def test_openai_ads_insights_params_and_rows() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.headers["Authorization"] == "Bearer oa-key"
        if request.url.path.endswith("/insights"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "date": "2026-08-01",
                            "campaign_id": "cmp_1",
                            "campaign_name": "Launch",
                            "spend": "12.50",
                            "impressions": 300,
                            "clicks": 9,
                            "conversions": 2,
                            "conversion_value": "80",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = OpenAIAdsReadProvider(api_key=SecretStr("oa-key"), client_factory=_factory(handler))
    entry = _catalog().get("openai_ads__get_campaign_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "acct_1", "start_date": "2026-08-01", "end_date": "2026-08-07"}
    )
    params = seen[0].url.params
    assert (
        params["aggregation_level"] == "campaign"
        and params["time_ranges[]"] == "2026-08-01..2026-08-07"
    )
    assert params.get_list("fields[]") == [
        "spend",
        "impressions",
        "clicks",
        "conversions",
        "conversion_value",
    ]
    assert result.payload["rows"][0]["conversion_value"] == "80"


async def test_composite_provider_routes_by_platform() -> None:
    class Stub:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def call_read(self, entry: Any, arguments: dict[str, Any]) -> Any:
            from paid_media_agent.tools.providers import ProviderResult

            return ProviderResult(payload={"from": self.tag})

    composite = CompositeReadProvider(Stub("pipeboard"), {Platform.LINKEDIN_ADS: Stub("linkedin")})
    catalog = _catalog()
    li = catalog.get("linkedin_ads__list_campaigns")
    x = catalog.get("x_ads__list_campaigns")
    assert li is not None and x is not None
    assert (await composite.call_read(li, {})).payload["from"] == "linkedin"
    assert (await composite.call_read(x, {})).payload["from"] == "pipeboard"
    with pytest.raises(ProviderError):
        await CompositeReadProvider(None, {}).call_read(x, {})


def test_errors_never_carry_credentials() -> None:
    from paid_media_agent.tools.direct._http import raise_for_status

    response = httpx.Response(
        401,
        request=httpx.Request(
            "GET",
            "https://api.linkedin.com/x",
            headers={"Authorization": "Bearer secret-token-value"},
        ),
    )
    with pytest.raises(ProviderError) as info:
        raise_for_status(response, context="linkedin")
    assert "secret-token-value" not in str(info.value) and "401" in str(info.value)
    assert json.dumps(str(info.value))


async def test_linkedin_creative_grain_pivots_the_same_analytics_call() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/rest/adAnalytics":
            return httpx.Response(
                200,
                json={
                    "elements": [
                        {
                            "dateRange": {"start": {"year": 2026, "month": 8, "day": 2}},
                            "pivotValues": ["urn:li:sponsoredCreative:9001"],
                            "impressions": 300,
                            "clicks": 9,
                            "costInLocalCurrency": "12.25",
                            "externalWebsiteConversions": 1,
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"elements": []})

    provider = LinkedInReadProvider(access_token=SecretStr("t"), client_factory=_factory(handler))
    entry = _catalog().get("linkedin_ads__get_creative_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "123", "start_date": "2026-08-01", "end_date": "2026-08-07"}
    )
    assert "pivot=CREATIVE" in str(next(r.url for r in seen if r.url.path == "/rest/adAnalytics"))
    assert result.payload["entity_type"] == "creative"
    row = result.payload["rows"][0]
    assert (row["creative_id"], row["spend"], row["conversions"]) == ("9001", "12.25", 1)


async def test_x_ad_group_grain_uses_line_items() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/line_items"):
            return httpx.Response(
                200, json={"data": [{"id": "li1", "name": "Group 1", "campaign_id": "c1"}]}
            )
        if request.url.path.endswith("/campaigns"):
            return httpx.Response(200, json={"data": [{"id": "c1", "name": "Camp"}]})
        if "/stats/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "id": "li1",
                            "id_data": [
                                {
                                    "metrics": {
                                        "impressions": [10, 20],
                                        "clicks": [1, 2],
                                        "billed_charge_local_micro": [1_000_000, 2_000_000],
                                    }
                                }
                            ],
                        }
                    ]
                },
            )
        return httpx.Response(404)

    provider = XAdsReadProvider(
        consumer_key="ck",
        consumer_secret=SecretStr("cs"),
        access_token=SecretStr("at"),
        access_token_secret=SecretStr("as"),
        client_factory=_factory(handler),
    )
    entry = _catalog().get("x_ads__get_ad_group_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "acc", "start_date": "2026-08-01", "end_date": "2026-08-02"}
    )
    stats = next(r for r in seen if "/stats/" in r.url.path)
    assert stats.url.params["entity"] == "LINE_ITEM" and stats.url.params["entity_ids"] == "li1"
    assert result.payload["entity_type"] == "ad_group"
    first = result.payload["rows"][0]
    assert (first["line_item_id"], first["campaign_id"], first["spend_micros"]) == (
        "li1",
        "c1",
        1_000_000.0,
    )


async def test_openai_ads_ad_group_grain_aggregates_by_ad_group() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "date": "2026-08-01",
                        "campaign_id": "c1",
                        "ad_group_id": "g1",
                        "ad_group_name": "Group",
                        "spend": "5.5",
                        "impressions": 100,
                        "clicks": 4,
                        "conversions": 1,
                    }
                ]
            },
        )

    provider = OpenAIAdsReadProvider(api_key=SecretStr("k"), client_factory=_factory(handler))
    entry = _catalog().get("openai_ads__get_ad_group_performance")
    assert entry is not None
    result = await provider.call_read(
        entry, {"account_id": "a1", "start_date": "2026-08-01", "end_date": "2026-08-07"}
    )
    assert seen[0].url.params["aggregation_level"] == "ad_group"
    assert result.payload["entity_type"] == "ad_group"
    assert result.payload["rows"][0]["ad_group_id"] == "g1"
