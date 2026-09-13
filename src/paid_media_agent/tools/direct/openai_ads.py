"""OpenAI Ads API reads: account, campaigns, and daily campaign insights."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import SecretStr

from paid_media_agent.config import Settings
from paid_media_agent.domain.common import JsonValue, Platform
from paid_media_agent.tools.catalog import CatalogEntry, RawTool
from paid_media_agent.tools.direct._http import (
    ClientFactory,
    default_client_factory,
    raise_for_status,
    require_id,
    require_window,
    wrap_transport_error,
)
from paid_media_agent.tools.providers import ProviderError, ProviderResult

OPENAI_ADS_API_BASE = "https://api.ads.openai.com/v1"
ENDPOINT = "direct://openai_ads"
INSIGHT_FIELDS = (
    "readable_time",
    "spend",
    "impressions",
    "clicks",
    "conversions",
    "order_created_attributed_sales",
)
MAX_PAGES = 50


def _schema(extra: dict[str, JsonValue], required: list[str]) -> dict[str, JsonValue]:
    props: dict[str, JsonValue] = {
        "account_id": {"type": "string", "description": "OpenAI Ads account id"}
    }
    props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": ["account_id", *required],
        "additionalProperties": False,
    }


def openai_ads_raw_tools() -> list[RawTool]:
    read = {"readOnlyHint": True, "destructiveHint": False}
    return [
        RawTool(
            platform=Platform.OPENAI_ADS.value,
            name="list_ad_accounts",
            description="Return the OpenAI Ads account the configured key belongs to.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.OPENAI_ADS.value,
            name="list_campaigns",
            description="List OpenAI Ads campaigns with status and budget.",
            input_schema=_schema({"status": {"type": "string"}}, []),
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.OPENAI_ADS.value,
            name="get_ad_group_performance",
            description="Daily ad group insights with the parent campaign id for an inclusive date range.",
            input_schema=_schema(
                {
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                },
                ["start_date", "end_date"],
            ),
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.OPENAI_ADS.value,
            name="get_campaign_performance",
            description="Daily campaign insights (spend, impressions, clicks, conversions, value) for an inclusive date range.",
            input_schema=_schema(
                {
                    "start_date": {"type": "string", "format": "date"},
                    "end_date": {"type": "string", "format": "date"},
                },
                ["start_date", "end_date"],
            ),
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
    ]


class OpenAIAdsReadProvider:
    def __init__(self, *, api_key: SecretStr, client_factory: ClientFactory | None = None) -> None:
        self._api_key = api_key
        self._client_factory = client_factory or default_client_factory()

    @classmethod
    def from_settings(cls, settings: Settings) -> OpenAIAdsReadProvider:
        if settings.openai_ads_api_key is None:
            raise ProviderError("OPENAI_ADS_API_KEY is not configured")
        return cls(api_key=settings.openai_ads_api_key)

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: Mapping[str, str | list[str]],
        *,
        context: str,
    ) -> dict[str, Any]:
        try:
            response = await client.get(
                f"{OPENAI_ADS_API_BASE}{path}",
                params=dict(params),
                headers={"Authorization": f"Bearer {self._api_key.get_secret_value()}"},
            )
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, context=context) from None
        raise_for_status(response, context=context)
        body = response.json()
        if not isinstance(body, dict):
            raise ProviderError(f"{context}: malformed response")
        return body

    async def _pages(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, str | list[str]],
        *,
        context: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursors: set[str] = set()
        for _ in range(MAX_PAGES):
            body = await self._get(client, path, params, context=context)
            data = body.get("data")
            if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
                raise ProviderError(f"{context}: malformed data")
            rows.extend(data)
            if not body.get("has_more"):
                return rows
            cursor = body.get("last_id")
            if not isinstance(cursor, str) or not cursor or cursor in cursors:
                raise ProviderError(f"{context}: invalid pagination cursor")
            cursors.add(cursor)
            params = {**params, "after": cursor}
        raise ProviderError(f"{context}: too many pages; narrow the date range")

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        async with self._client_factory() as client:
            if entry.name == "list_ad_accounts":
                body = await self._get(client, "/ad_account", {}, context="openai ads account")
                data = body.get("data")
                account: dict[str, Any] = data if isinstance(data, dict) else body
                return ProviderResult(
                    payload={
                        "accounts": [
                            {
                                "id": account.get("id"),
                                "name": account.get("name"),
                                "currency": account.get("currency"),
                                "timezone": account.get("timezone"),
                            }
                        ]
                    }
                )
            account_id = require_id(arguments.get("account_id"), name="account_id")
            if entry.name == "list_campaigns":
                campaigns = await self._pages(
                    client, "/campaigns", {"limit": "100"}, context="openai ads campaigns"
                )
                status = arguments.get("status")
                listed: list[dict[str, JsonValue]] = [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "status": c.get("status"),
                        "daily_budget": c.get("daily_budget"),
                        "currency": c.get("currency"),
                    }
                    for c in campaigns
                    if isinstance(c, dict) and (status is None or c.get("status") == status)
                ]
                return ProviderResult(payload={"campaigns": listed, "account_id": account_id})
            if entry.name in ("get_campaign_performance", "get_ad_group_performance"):
                ad_groups = entry.name == "get_ad_group_performance"
                start, end = require_window(arguments.get("start_date"), arguments.get("end_date"))
                params: dict[str, str | list[str]] = {
                    "aggregation_level": "ad_group" if ad_groups else "campaign",
                    "time_granularity": "daily",
                    "time_ranges[]": json.dumps(
                        {"type": "date_range", "since": start.isoformat(), "until": end.isoformat()}
                    ),
                    "limit": "2000",
                    "fields[]": [
                        "campaign_id",
                        "campaign_name",
                        *(["ad_group_id", "ad_group_name"] if ad_groups else []),
                        *INSIGHT_FIELDS,
                    ],
                }
                data = await self._pages(
                    client, "/ad_account/insights", params, context="openai ads insights"
                )
                rows: list[dict[str, JsonValue]] = []
                for item in data:
                    day = item.get("readable_time")
                    entity_id = item.get("ad_group_id" if ad_groups else "campaign_id")
                    if not isinstance(day, str) or not entity_id:
                        raise ProviderError(
                            "openai ads insights: row is missing its date or entity"
                        )
                    rows.append(
                        {
                            "date": day[:10],
                            "campaign_id": str(item.get("campaign_id") or item.get("id") or ""),
                            "campaign_name": item.get("campaign_name") or item.get("name") or "",
                            **(
                                {
                                    "ad_group_id": str(item.get("ad_group_id") or ""),
                                    "ad_group_name": item.get("ad_group_name") or "",
                                }
                                if ad_groups
                                else {}
                            ),
                            "spend": item.get("spend"),
                            "impressions": item.get("impressions"),
                            "clicks": item.get("clicks"),
                            "conversions": item.get("conversions"),
                            "conversion_value": item.get("order_created_attributed_sales"),
                        }
                    )
                return ProviderResult(
                    payload={
                        "rows": rows,
                        "entity_type": "ad_group" if ad_groups else "campaign",
                        "attribution": "openai_ads_reported_conversions",
                    }
                )
        raise ProviderError("openai ads read tool not implemented")
