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
TRADE_MAX_PRICE_AGE = timedelta(minutes=30)
TRADE_MAX_FX_AGE = timedelta(hours=2)
TRADE_MAX_SOURCE_SKEW = timedelta(minutes=90)


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


def trade_quote_context(
    *, price: Any, price_at: datetime | None, row_quote: str | None,
    catalog_quote: str | None, usd_fx: dict[str, Any] | None,
    quote_fx: dict[str, Any] | None, require_usd: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Fail closed unless a Paper trade has a priced, dated common EUR unit."""
    now = _utc(now or datetime.now(timezone.utc))
    quote = str(row_quote or "").upper()
    if quote not in {"EUR", "USD", "USDT"} or quote != str(catalog_quote or "").upper():
        return {"reason": "market_quote_unverified"}
    if not recent_positive(price, price_at, now=now, max_age=TRADE_MAX_PRICE_AGE):
        return {"reason": "market_price_stale"}
    if require_usd and (not usd_fx or not recent_positive(
        usd_fx.get("eur_per_unit"), usd_fx.get("observed_at"),
        now=now, max_age=TRADE_MAX_FX_AGE,
    )):
        return {"reason": "usd_eur_fx_unavailable"}
    if quote == "EUR":
        market_factor, market_fx_at = 1.0, None
    else:
        if not quote_fx or not recent_positive(
            quote_fx.get("eur_per_unit"), quote_fx.get("observed_at"),
            now=now, max_age=TRADE_MAX_FX_AGE,
        ):
            return {"reason": "market_quote_eur_fx_unavailable"}
        market_factor = float(quote_fx["eur_per_unit"])
        market_fx_at = _utc(quote_fx["observed_at"])
    moments = [_utc(price_at)]
    if require_usd:
        moments.append(_utc(usd_fx["observed_at"]))
    if market_fx_at is not None:
        moments.append(market_fx_at)
    if max(moments) - min(moments) > TRADE_MAX_SOURCE_SKEW:
        return {"reason": "trade_quote_sources_out_of_sync"}
    market_eur = float(price) * market_factor
    if not math.isfinite(market_eur) or market_eur <= 0:
        return {"reason": "market_conversion_invalid"}
    return {
        "reason": None, "quote_currency": quote,
        "market_price_eur": market_eur, "market_price": float(price),
        "market_price_at": _utc(price_at),
        "market_fx_eur_per_unit": market_factor,
        "market_fx_as_of": market_fx_at,
        "usd_fx_eur_per_unit": float(usd_fx["eur_per_unit"]) if require_usd else None,
        "usd_fx_as_of": _utc(usd_fx["observed_at"]) if require_usd else None,
    }


def inverted_eur_quote(value: Any, observed_at: datetime | None, *, now: datetime | None = None) -> float | None:
    """Convert a dated EUR/USD or EUR/USDT quote to EUR per quote unit."""
    now = now or datetime.now(timezone.utc)
    if not recent_positive(value, observed_at, now=now, max_age=MAX_FX_AGE):
        return None
    factor = 1.0 / float(value)
    return factor if math.isfinite(factor) and factor > 0 else None
