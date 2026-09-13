"""Direct X and OpenAI Ads adapters: request shape, auth, and normalization."""

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
from paid_media_agent.tools.direct.openai_ads import OpenAIAdsReadProvider, openai_ads_raw_tools
from paid_media_agent.tools.direct.x_ads import (
    XAdsReadProvider,
    oauth1_header,
    stats_windows,
    x_ads_raw_tools,
)
from paid_media_agent.tools.providers import ProviderError


def _factory(handler: Any) -> Any:
    return lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _catalog() -> Any:
    return build_authorized_catalog([*x_ads_raw_tools(), *openai_ads_raw_tools()], source="direct")


def test_direct_tools_classify_as_reads_with_account_scope() -> None:
    catalog = _catalog()
    names = {e.qualified_name: e for e in catalog.read_entries()}
    assert "x_ads__get_campaign_performance" in names
    assert "openai_ads__list_campaigns" in names
    denied = {e.qualified_name: e.policy.reason for e in catalog.denied_entries()}
    assert denied["x_ads__list_ad_accounts"] == "no_account_scope", "account listing is host-only"


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
                            "readable_time": "2026-08-01",
                            "campaign_id": "cmp_1",
                            "campaign_name": "Launch",
                            "spend": "12.50",
                            "impressions": 300,
                            "clicks": 9,
                            "conversions": 2,
                            "order_created_attributed_sales": "80",
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
        and params["time_granularity"] == "daily"
        and json.loads(params["time_ranges[]"])
        == {"type": "date_range", "since": "2026-08-01", "until": "2026-08-07"}
    )
    assert params.get_list("fields[]") == [
        "campaign_id",
        "campaign_name",
        "readable_time",
        "spend",
        "impressions",
        "clicks",
        "conversions",
        "order_created_attributed_sales",
    ]
    assert result.payload["rows"][0]["conversion_value"] == "80"


async def test_composite_provider_routes_by_platform() -> None:
    class Stub:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        async def call_read(self, entry: Any, arguments: dict[str, Any]) -> Any:
            from paid_media_agent.tools.providers import ProviderResult

            return ProviderResult(payload={"from": self.tag})

    composite = CompositeReadProvider(Stub("pipeboard"), {Platform.OPENAI_ADS: Stub("openai")})
    catalog = _catalog()
    li = catalog.get("openai_ads__list_campaigns")
    x = catalog.get("x_ads__list_campaigns")
    assert li is not None and x is not None
    assert (await composite.call_read(li, {})).payload["from"] == "openai"
    assert (await composite.call_read(x, {})).payload["from"] == "pipeboard"
    with pytest.raises(ProviderError):
        await CompositeReadProvider(None, {}).call_read(x, {})


def test_errors_never_carry_credentials() -> None:
    from paid_media_agent.tools.direct._http import raise_for_status

    response = httpx.Response(
        401,
        request=httpx.Request(
            "GET",
            "https://ads-api.x.com/12/accounts",
            headers={"Authorization": "Bearer secret-token-value"},
        ),
    )
    with pytest.raises(ProviderError) as info:
        raise_for_status(response, context="x")
    assert "secret-token-value" not in str(info.value) and "401" in str(info.value)
    assert json.dumps(str(info.value))


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
                        "readable_time": "2026-08-01",
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


def test_direct_platforms_require_complete_credentials() -> None:
    settings = Settings(_env_file=None, openai_ads_api_key="key", x_ads_consumer_key="partial")  # type: ignore[call-arg]
    assert configured_direct_platforms(settings) == (Platform.OPENAI_ADS,)
    assert {t.platform for t in direct_raw_tools(settings)} == {"openai_ads"}
    assert set(direct_read_providers(settings)) == {Platform.OPENAI_ADS}


async def test_openai_ads_paginates_and_rejects_incomplete_results() -> None:
    repeat_cursor = False

    def handler(request: httpx.Request) -> httpx.Response:
        if "after" in request.url.params:
            if repeat_cursor:
                return httpx.Response(200, json={"data": [], "has_more": True, "last_id": "page1"})
            return httpx.Response(200, json={"data": [{"id": "c2"}], "has_more": False})
        return httpx.Response(
            200, json={"data": [{"id": "c1"}], "has_more": True, "last_id": "page1"}
        )

    provider = OpenAIAdsReadProvider(api_key=SecretStr("key"), client_factory=_factory(handler))
    entry = _catalog().get("openai_ads__list_campaigns")
    assert entry is not None
    result = await provider.call_read(entry, {"account_id": "account"})
    assert [row["id"] for row in result.payload["campaigns"]] == ["c1", "c2"]
    repeat_cursor = True
    with pytest.raises(ProviderError, match="pagination cursor"):
        await provider.call_read(entry, {"account_id": "account"})
