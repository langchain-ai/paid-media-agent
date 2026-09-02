"""Shared HTTP helpers for direct adapters: bounded clients, strict input checks, sanitized errors."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date

import httpx

from paid_media_agent.middleware.redaction import sanitize_exception
from paid_media_agent.tools.providers import ProviderError, ProviderTimeout

DEFAULT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_ID_RE = re.compile(r"^[A-Za-z0-9_\-:]{1,64}$")
_DIGITS_RE = re.compile(r"^[0-9]{1,32}$")

ClientFactory = Callable[[], httpx.AsyncClient]


def default_client_factory(timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> ClientFactory:
    return lambda: httpx.AsyncClient(timeout=timeout)


def require_id(value: object, *, name: str, digits_only: bool = False) -> str:
    """Accept only identifier-shaped strings so a value can never smuggle query syntax."""
    text = str(value or "").strip()
    pattern = _DIGITS_RE if digits_only else _ID_RE
    if not pattern.match(text):
        raise ProviderError(f"{name} is not a valid identifier")
    return text


def require_window(start: object, end: object, *, max_days: int = 400) -> tuple[date, date]:
    try:
        start_date = date.fromisoformat(str(start))
        end_date = date.fromisoformat(str(end))
    except (TypeError, ValueError):
        raise ProviderError("start_date and end_date must be ISO dates") from None
    if end_date < start_date:
        raise ProviderError("end_date precedes start_date")
    if (end_date - start_date).days + 1 > max_days:
        raise ProviderError(f"window exceeds {max_days} days")
    return start_date, end_date


def raise_for_status(response: httpx.Response, *, context: str) -> None:
    """Turn a non-2xx response into a bounded, secret-free provider error."""
    if 200 <= response.status_code < 300:
        return
    if response.status_code in (401, 403):
        raise ProviderError(
            f"{context}: provider rejected the credentials (HTTP {response.status_code})"
        )
    if response.status_code == 429:
        raise ProviderError(f"{context}: provider rate limit (HTTP 429)")
    raise ProviderError(f"{context}: provider returned HTTP {response.status_code}")


def wrap_transport_error(exc: Exception, *, context: str) -> ProviderError:
    if isinstance(exc, httpx.TimeoutException):
        return ProviderTimeout(f"{context}: provider timed out")
    return ProviderError(f"{context}: {sanitize_exception(exc)[:160]}")
