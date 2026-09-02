"""LinkedIn Marketing API reads: ad accounts, campaigns, and daily campaign analytics."""

from __future__ import annotations

from datetime import date
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

LINKEDIN_API_BASE = "https://api.linkedin.com"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"  # noqa: S105 - public endpoint, not a secret
LINKEDIN_API_VERSION = "202601"
_ANALYTICS_FIELDS = (
    "dateRange,pivotValues,impressions,clicks,costInLocalCurrency,"
    "externalWebsiteConversions,externalWebsitePostClickConversions,oneClickLeads"
)
_ROW_CAP = 15_000
ENDPOINT = "direct://linkedin_ads"


def _schema(extra: dict[str, JsonValue], required: list[str]) -> dict[str, JsonValue]:
    props: dict[str, JsonValue] = {
        "account_id": {"type": "string", "description": "Sponsored account id"}
    }
    props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": ["account_id", *required],
        "additionalProperties": False,
    }


def linkedin_raw_tools() -> list[RawTool]:
    read = {"readOnlyHint": True, "destructiveHint": False}
    return [
        RawTool(
            platform=Platform.LINKEDIN_ADS.value,
            name="list_ad_accounts",
            description="List LinkedIn ad accounts visible to the configured token, with currency and status.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.LINKEDIN_ADS.value,
            name="list_campaigns",
            description="List LinkedIn campaigns (sponsoredCampaign) in an account with status and daily budget.",
            input_schema=_schema({"status": {"type": "string"}}, []),
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.LINKEDIN_ADS.value,
            name="get_campaign_performance",
            description=(
                "Daily campaign analytics from adAnalytics (impressions, clicks, cost in account currency, "
                "external website conversions) for an inclusive date range."
            ),
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


def _date_range(start: date, end: date) -> str:
    """Rest.li dateRange literal. Built only from validated dates, appended unencoded on purpose."""
    return (
        f"dateRange=(start:(year:{start.year},month:{start.month},day:{start.day}),"
        f"end:(year:{end.year},month:{end.month},day:{end.day}))"
    )


def _ymd(node: Any) -> date | None:
    if not isinstance(node, dict):
        return None
    try:
        return date(int(node["year"]), int(node["month"]), int(node["day"]))
    except (KeyError, TypeError, ValueError):
        return None


class LinkedInReadProvider:
    """Bearer-token client with one refresh attempt on 401. Tokens never leave the process."""

    def __init__(
        self,
        *,
        access_token: SecretStr,
        refresh_token: SecretStr | None = None,
        client_id: str | None = None,
        client_secret: SecretStr | None = None,
        client_factory: ClientFactory | None = None,
        api_version: str = LINKEDIN_API_VERSION,
    ) -> None:
        self._access_token = access_token
        self._refresh_token = refresh_token
        self._client_id = client_id
        self._client_secret = client_secret
        self._client_factory = client_factory or default_client_factory()
        self._api_version = api_version

    @classmethod
    def from_settings(cls, settings: Settings) -> LinkedInReadProvider:
        if settings.linkedin_access_token is None:
            raise ProviderError("LINKEDIN_ACCESS_TOKEN is not configured")
        return cls(
            access_token=settings.linkedin_access_token,
            refresh_token=settings.linkedin_refresh_token,
            client_id=settings.linkedin_client_id,
            client_secret=settings.linkedin_client_secret,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token.get_secret_value()}",
            "LinkedIn-Version": self._api_version,
            "X-Restli-Protocol-Version": "2.0.0",
        }

    async def _refresh(self, client: httpx.AsyncClient) -> bool:
        if self._refresh_token is None or not self._client_id or self._client_secret is None:
            return False
        response = await client.post(
            LINKEDIN_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token.get_secret_value(),
                "client_id": self._client_id,
                "client_secret": self._client_secret.get_secret_value(),
            },
        )
        if response.status_code != 200:
            return False
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            return False
        self._access_token = SecretStr(token)
        if isinstance(body.get("refresh_token"), str):
            self._refresh_token = SecretStr(body["refresh_token"])
        return True

    async def _get(
        self, client: httpx.AsyncClient, path: str, query: str, *, context: str
    ) -> dict[str, Any]:
        url = f"{LINKEDIN_API_BASE}{path}?{query}" if query else f"{LINKEDIN_API_BASE}{path}"
        try:
            response = await client.get(url, headers=self._headers())
            if response.status_code == 401 and await self._refresh(client):
                response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, context=context) from None
        raise_for_status(response, context=context)
        body = response.json()
        if not isinstance(body, dict):
            raise ProviderError(f"{context}: malformed response")
        return body

    async def _paged_elements(
        self, client: httpx.AsyncClient, path: str, base_query: str, *, context: str
    ) -> list[dict[str, Any]]:
        elements: list[dict[str, Any]] = []
        token: str | None = None
        seen: set[str] = set()
        for _ in range(50):
            query = f"{base_query}&pageToken={token}" if token else base_query
            body = await self._get(client, path, query, context=context)
            page = body.get("elements")
            if not isinstance(page, list):
                raise ProviderError(f"{context}: malformed elements")
            elements.extend(item for item in page if isinstance(item, dict))
            token = (
                (body.get("metadata") or {}).get("nextPageToken")
                if isinstance(body.get("metadata"), dict)
                else None
            )
            if not token or token in seen:
                break
            seen.add(token)
        return elements

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        async with self._client_factory() as client:
            if entry.name == "list_ad_accounts":
                body = await self._get(
                    client, "/v2/adAccountsV2", "q=search&count=50", context="linkedin accounts"
                )
                accounts = [
                    {
                        "id": str(el.get("id")),
                        "name": el.get("name"),
                        "status": el.get("status"),
                        "currency": el.get("currency"),
                    }
                    for el in body.get("elements", [])
                    if isinstance(el, dict) and el.get("id") is not None
                ]
                return ProviderResult(payload={"accounts": accounts})
            account = require_id(arguments.get("account_id"), name="account_id", digits_only=True)
            if entry.name == "list_campaigns":
                elements = await self._paged_elements(
                    client,
                    f"/rest/adAccounts/{account}/adCampaigns",
                    "q=search&count=100",
                    context="linkedin campaigns",
                )
                status = arguments.get("status")
                campaigns = [
                    {
                        "id": str(el.get("id")),
                        "name": el.get("name"),
                        "status": el.get("status"),
                        "daily_budget": (el.get("dailyBudget") or {}).get("amount")
                        if isinstance(el.get("dailyBudget"), dict)
                        else None,
                        "currency": (el.get("dailyBudget") or {}).get("currencyCode")
                        if isinstance(el.get("dailyBudget"), dict)
                        else None,
                    }
                    for el in elements
                    if status is None or el.get("status") == status
                ]
                return ProviderResult(payload={"campaigns": campaigns})
            if entry.name == "get_campaign_performance":
                start, end = require_window(arguments.get("start_date"), arguments.get("end_date"))
                query = (
                    "q=analytics&pivot=CAMPAIGN&timeGranularity=DAILY"
                    f"&accounts=List(urn%3Ali%3AsponsoredAccount%3A{account})"
                    f"&{_date_range(start, end)}&fields={_ANALYTICS_FIELDS}"
                )
                body = await self._get(
                    client, "/rest/adAnalytics", query, context="linkedin analytics"
                )
                raw_elements = body.get("elements")
                if not isinstance(raw_elements, list):
                    raise ProviderError("linkedin analytics: malformed elements")
                analytics: list[Any] = raw_elements
                if len(analytics) >= _ROW_CAP:
                    raise ProviderError(
                        "linkedin analytics: response hit the 15,000 row cap; narrow the window"
                    )
                names = {
                    f"urn:li:sponsoredCampaign:{c.get('id')}": str(c.get("name") or "")
                    for c in await self._paged_elements(
                        client,
                        f"/rest/adAccounts/{account}/adCampaigns",
                        "q=search&count=100",
                        context="linkedin campaigns",
                    )
                }
                rows: list[dict[str, JsonValue]] = []
                for el in analytics:
                    if not isinstance(el, dict):
                        continue
                    day = (
                        _ymd((el.get("dateRange") or {}).get("start"))
                        if isinstance(el.get("dateRange"), dict)
                        else None
                    )
                    pivot = (el.get("pivotValues") or [None])[0]
                    if day is None or not isinstance(pivot, str):
                        continue
                    rows.append(
                        {
                            "date": day.isoformat(),
                            "campaign_id": pivot.rsplit(":", 1)[-1],
                            "campaign_name": names.get(pivot, pivot),
                            "spend": el.get("costInLocalCurrency"),
                            "impressions": el.get("impressions"),
                            "clicks": el.get("clicks"),
                            "conversions": el.get("externalWebsiteConversions"),
                        }
                    )
                return ProviderResult(
                    payload={"rows": rows, "attribution": "linkedin_external_website_conversions"}
                )
        raise ProviderError("linkedin read tool not implemented")
