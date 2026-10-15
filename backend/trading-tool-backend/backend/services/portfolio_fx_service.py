"""Dated quote-currency conversion for EUR-denominated portfolio ledgers.

An exchange's USDT quote is not EUR cash. A missing or stale conversion keeps
the position valuation unknown; no implicit USD/USDT parity is permitted.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any


MAX_PRICE_AGE = timedelta(hours=24)
MAX_FX_AGE = timedelta(hours=24)


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def recent_positive(value: Any, observed_at: datetime | None, *, now: datetime, max_age: timedelta) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    source_at = _utc(observed_at)
    age = _utc(now) - source_at if source_at is not None else None
    return bool(math.isfinite(number) and number > 0 and age is not None and timedelta(0) <= age <= max_age)


def price_in_eur(
    *, price: Any, price_at: datetime | None, quote_currency: str | None,
    fx: dict[str, Any] | None, now: datetime | None = None,
) -> tuple[float | None, datetime | None, float | None, datetime | None]:
    """Return EUR unit price, oldest source moment, FX factor and FX moment."""
    now = now or datetime.now(timezone.utc)
    if not recent_positive(price, price_at, now=now, max_age=MAX_PRICE_AGE):
        return None, None, None, None
    quote = str(quote_currency or "").upper()
    if quote == "EUR":
        return float(price), _utc(price_at), 1.0, None
    if quote not in {"USD", "USDT"} or not fx:
        return None, None, None, None
    factor = fx.get("eur_per_unit")
    fx_at = fx.get("observed_at")
    if not recent_positive(factor, fx_at, now=now, max_age=MAX_FX_AGE):
        return None, None, None, None
    converted = float(price) * float(factor)
    if not math.isfinite(converted) or converted <= 0:
        return None, None, None, None
    return converted, min(_utc(price_at), _utc(fx_at)), float(factor), _utc(fx_at)


def inverted_eur_quote(value: Any, observed_at: datetime | None, *, now: datetime | None = None) -> float | None:
    """Convert a dated EUR/USD or EUR/USDT quote to EUR per quote unit."""
    now = now or datetime.now(timezone.utc)
    if not recent_positive(value, observed_at, now=now, max_age=MAX_FX_AGE):
        return None
    factor = 1.0 / float(value)
    return factor if math.isfinite(factor) and factor > 0 else None
