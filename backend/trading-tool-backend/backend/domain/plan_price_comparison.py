"""Typed, read-only comparison between a saved entry and a market snapshot."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any


def _moment(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def compare_plan_entry_with_market(
    strategy: dict[str, Any], market: dict[str, Any] | None,
    *, now: datetime | None = None,
) -> dict[str, Any]:
    """Never infer parity between USD and USDT or trust an undated quote."""
    unavailable = {
        "status": "unavailable", "setup_id": strategy.get("setup_id"),
        "strategy_id": strategy.get("strategy_id"), "symbol": strategy.get("symbol"),
    }
    if strategy.get("price_currency_status") != "confirmed":
        return {**unavailable, "reason": "plan_currency_unconfirmed"}
    if not market or str(market.get("symbol") or "").upper() != str(strategy.get("symbol") or "").upper():
        return {**unavailable, "reason": "matching_market_price_unavailable"}
    plan_quote = str(strategy.get("price_currency") or "").upper()
    market_quote = str(market.get("quote_currency") or "").upper()
    if plan_quote not in {"EUR", "USD", "USDT"} or market_quote not in {"EUR", "USD", "USDT"}:
        return {**unavailable, "reason": "market_quote_unconfirmed"}
    if plan_quote != market_quote:
        return {**unavailable, "reason": "different_quote_currencies_without_verified_conversion"}
    observed_at = _moment(market.get("as_of") or market.get("source_observed_at"))
    current = _moment(now or datetime.now(timezone.utc))
    if observed_at is None or not timedelta(0) <= current - observed_at <= timedelta(minutes=30):
        return {**unavailable, "reason": "market_price_stale"}
    try:
        entry = float(strategy["entry"])
        price = float(market["price"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return {**unavailable, "reason": "price_values_unavailable"}
    if not math.isfinite(entry) or not math.isfinite(price) or entry <= 0 or price <= 0:
        return {**unavailable, "reason": "price_values_unavailable"}
    return {
        "status": "available", "setup_id": strategy.get("setup_id"),
        "strategy_id": strategy.get("strategy_id"), "symbol": strategy.get("symbol"),
        "entry": entry, "market_price": price, "quote_currency": plan_quote,
        "market_price_as_of": observed_at.isoformat(),
        "relation_to_entry": "above" if price > entry else "below" if price < entry else "equal",
    }
