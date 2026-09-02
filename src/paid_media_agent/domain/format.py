"""Presentation formatting owned by code, so model prose never rounds numbers itself."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

UNAVAILABLE = "unavailable"


def format_money(value: Decimal | None, currency: str) -> str:
    if value is None:
        return UNAVAILABLE
    quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{quantized:,.2f} {currency}"


def format_count(value: int | Decimal | None) -> str:
    if value is None:
        return UNAVAILABLE
    if isinstance(value, Decimal):
        if value == value.to_integral_value():
            return f"{int(value):,}"
        return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,}"
    return f"{value:,}"


def format_ratio(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return UNAVAILABLE
    quantum = Decimal(1).scaleb(-places)
    return f"{value.quantize(quantum, rounding=ROUND_HALF_UP)}"


def format_percent(value: Decimal | None, places: int = 1) -> str:
    """Format a fraction (0.123) as a percentage string (12.3%)."""
    if value is None:
        return UNAVAILABLE
    quantum = Decimal(1).scaleb(-places)
    pct = (value * Decimal(100)).quantize(quantum, rounding=ROUND_HALF_UP)
    sign = "+" if pct > 0 else ""
    return f"{sign}{pct}%"
