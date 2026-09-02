"""X Ads API reads: accounts, campaigns, and daily campaign stats with OAuth 1.0a signing."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import urllib.parse
from datetime import UTC, date, datetime, timedelta
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

X_ADS_API_BASE = "https://ads-api.x.com/12"
ENDPOINT = "direct://x_ads"
STATS_WINDOW_DAYS = 7
STATS_MAX_IDS = 20


def _schema(extra: dict[str, JsonValue], required: list[str]) -> dict[str, JsonValue]:
    props: dict[str, JsonValue] = {
        "account_id": {"type": "string", "description": "X Ads account id"}
    }
    props.update(extra)
    return {
        "type": "object",
        "properties": props,
        "required": ["account_id", *required],
        "additionalProperties": False,
    }


def x_ads_raw_tools() -> list[RawTool]:
    read = {"readOnlyHint": True, "destructiveHint": False}
    return [
        RawTool(
            platform=Platform.X_ADS.value,
            name="list_ad_accounts",
            description="List X Ads accounts accessible to the configured credentials, with currency and timezone.",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.X_ADS.value,
            name="list_campaigns",
            description="List X Ads campaigns in an account with entity status and daily budget.",
            input_schema=_schema({"status": {"type": "string"}}, []),
            annotations=read,
            source_endpoint=ENDPOINT,
        ),
        RawTool(
            platform=Platform.X_ADS.value,
            name="get_campaign_performance",
            description=(
                "Daily campaign stats (impressions, clicks, billed spend, web conversion purchases) for an "
                "inclusive date range. Windows are fetched in 7-day slices per the X Ads stats limit."
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


def _pct(value: str) -> str:
    return urllib.parse.quote(value, safe="-._~")


def oauth1_header(
    method: str,
    url: str,
    params: dict[str, str],
    *,
    consumer_key: str,
    consumer_secret: str,
    token: str,
    token_secret: str,
    nonce: str | None = None,
    timestamp: str | None = None,
) -> str:
    """OAuth 1.0a HMAC-SHA1 Authorization header (RFC 5849) built with the standard library."""
    oauth: dict[str, str] = {
        "oauth_consumer_key": consumer_key,
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": timestamp or str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    normalized = "&".join(f"{_pct(k)}={_pct(v)}" for k, v in sorted({**params, **oauth}.items()))
    base = "&".join([method.upper(), _pct(url), _pct(normalized)])
    key = f"{_pct(consumer_secret)}&{_pct(token_secret)}".encode()
    digest = hmac.new(key, base.encode(), hashlib.sha1).digest()  # noqa: S324 - HMAC-SHA1 is the OAuth 1.0a contract
    oauth["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(f'{k}="{_pct(v)}"' for k, v in sorted(oauth.items()))


def stats_windows(start: date, end: date) -> list[tuple[str, str]]:
    """Inclusive date window as UTC-midnight slices no longer than the stats API allows."""
    cursor = datetime(start.year, start.month, start.day, tzinfo=UTC)
    stop = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
    windows: list[tuple[str, str]] = []
    while cursor < stop:
        window_end = min(cursor + timedelta(days=STATS_WINDOW_DAYS), stop)
        windows.append(
            (cursor.strftime("%Y-%m-%dT%H:%M:%SZ"), window_end.strftime("%Y-%m-%dT%H:%M:%SZ"))
        )
        cursor = window_end
    return windows


def _sum_series(values: Any) -> float | None:
    if not isinstance(values, list):
        return None
    return float(sum(float(v) for v in values if v is not None))


class XAdsReadProvider:
    def __init__(
        self,
        *,
        consumer_key: str,
        consumer_secret: SecretStr,
        access_token: SecretStr,
        access_token_secret: SecretStr,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._access_token = access_token
        self._access_token_secret = access_token_secret
        self._client_factory = client_factory or default_client_factory()

    @classmethod
    def from_settings(cls, settings: Settings) -> XAdsReadProvider:
        if (
            settings.x_ads_consumer_key is None
            or settings.x_ads_consumer_secret is None
            or settings.x_ads_access_token is None
            or settings.x_ads_access_token_secret is None
        ):
            raise ProviderError("X Ads credentials are not fully configured")
        return cls(
            consumer_key=settings.x_ads_consumer_key.get_secret_value(),
            consumer_secret=settings.x_ads_consumer_secret,
            access_token=settings.x_ads_access_token,
            access_token_secret=settings.x_ads_access_token_secret,
        )

    async def _get(
        self, client: httpx.AsyncClient, path: str, params: dict[str, str], *, context: str
    ) -> dict[str, Any]:
        url = f"{X_ADS_API_BASE}{path}"
        header = oauth1_header(
            "GET",
            url,
            params,
            consumer_key=self._consumer_key,
            consumer_secret=self._consumer_secret.get_secret_value(),
            token=self._access_token.get_secret_value(),
            token_secret=self._access_token_secret.get_secret_value(),
        )
        try:
            response = await client.get(url, params=params, headers={"Authorization": header})
        except httpx.HTTPError as exc:
            raise wrap_transport_error(exc, context=context) from None
        raise_for_status(response, context=context)
        body = response.json()
        if not isinstance(body, dict):
            raise ProviderError(f"{context}: malformed response")
        return body

    async def _list(
        self, client: httpx.AsyncClient, path: str, *, context: str
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        for _ in range(50):
            params = {"count": "1000"}
            if cursor:
                params["cursor"] = cursor
            body = await self._get(client, path, params, context=context)
            page = body.get("data")
            if not isinstance(page, list):
                raise ProviderError(f"{context}: malformed data")
            rows.extend(item for item in page if isinstance(item, dict))
            cursor = str(body.get("next_cursor") or "")
            if not cursor or cursor == "0" or cursor in seen:
                break
            seen.add(cursor)
        return rows

    async def call_read(
        self, entry: CatalogEntry, arguments: dict[str, JsonValue]
    ) -> ProviderResult:
        async with self._client_factory() as client:
            if entry.name == "list_ad_accounts":
                body = await self._get(client, "/accounts", {"count": "200"}, context="x accounts")
                accounts = [
                    {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "timezone": a.get("timezone"),
                        "currency": a.get("currency"),
                        "approval_status": a.get("approval_status"),
                    }
                    for a in body.get("data", [])
                    if isinstance(a, dict)
                ]
                return ProviderResult(payload={"accounts": accounts})
            account = require_id(arguments.get("account_id"), name="account_id")
            campaigns = await self._list(
                client, f"/accounts/{account}/campaigns", context="x campaigns"
            )
            if entry.name == "list_campaigns":
                status = arguments.get("status")
                listed: list[dict[str, JsonValue]] = [
                    {
                        "id": c.get("id"),
                        "name": c.get("name"),
                        "status": c.get("entity_status"),
                        "daily_budget": (float(c["daily_budget_amount_local_micro"]) / 1_000_000)
                        if c.get("daily_budget_amount_local_micro") is not None
                        else None,
                        "currency": c.get("currency"),
                    }
                    for c in campaigns
                    if status is None or c.get("entity_status") == status
                ]
                return ProviderResult(payload={"campaigns": listed})
            if entry.name == "get_campaign_performance":
                start, end = require_window(
                    arguments.get("start_date"), arguments.get("end_date"), max_days=93
                )
                names = {
                    str(c.get("id")): str(c.get("name") or "") for c in campaigns if c.get("id")
                }
                ids = list(names)
                rows: list[dict[str, JsonValue]] = []
                for window_start, window_end in stats_windows(start, end):
                    for i in range(0, len(ids), STATS_MAX_IDS):
                        chunk = ids[i : i + STATS_MAX_IDS]
                        params = {
                            "entity": "CAMPAIGN",
                            "entity_ids": ",".join(chunk),
                            "start_time": window_start,
                            "end_time": window_end,
                            "granularity": "DAY",
                            "metric_groups": "ENGAGEMENT,BILLING,WEB_CONVERSION",
                            "placement": "ALL_ON_TWITTER",
                        }
                        body = await self._get(
                            client, f"/stats/accounts/{account}", params, context="x stats"
                        )
                        data = body.get("data")
                        if not isinstance(data, list):
                            raise ProviderError("x stats: malformed data")
                        day0 = datetime.strptime(window_start, "%Y-%m-%dT%H:%M:%SZ").date()
                        for item in data:
                            if not isinstance(item, dict):
                                continue
                            for entry_data in item.get("id_data", []):
                                metrics = (
                                    entry_data.get("metrics", {})
                                    if isinstance(entry_data, dict)
                                    else {}
                                )
                                impressions = metrics.get("impressions") or []
                                for offset in range(
                                    len(impressions) if isinstance(impressions, list) else 0
                                ):
                                    day = day0 + timedelta(days=offset)
                                    if day < start or day > end:
                                        continue
                                    purchases = metrics.get("conversion_purchases")
                                    conv = None
                                    if isinstance(purchases, dict):
                                        series = purchases.get("metric")
                                        conv = (
                                            float(series[offset])
                                            if isinstance(series, list)
                                            and offset < len(series)
                                            and series[offset] is not None
                                            else None
                                        )
                                    rows.append(
                                        {
                                            "date": day.isoformat(),
                                            "campaign_id": str(item.get("id")),
                                            "campaign_name": names.get(
                                                str(item.get("id")), str(item.get("id"))
                                            ),
                                            "spend_micros": _pick(
                                                metrics.get("billed_charge_local_micro"), offset
                                            ),
                                            "impressions": _pick(
                                                metrics.get("impressions"), offset
                                            ),
                                            "clicks": _pick(metrics.get("clicks"), offset),
                                            "conversions": conv,
                                        }
                                    )
                return ProviderResult(
                    payload={"rows": rows, "attribution": "x_web_conversion_purchases"}
                )
        raise ProviderError("x read tool not implemented")


def _pick(series: Any, offset: int) -> float | None:
    if isinstance(series, list) and offset < len(series) and series[offset] is not None:
        return float(series[offset])
    return None
