from __future__ import annotations

import os
import math
from datetime import datetime, timezone
from typing import Any

import requests


TWELVE_DATA_QUOTE_URL = "https://api.twelvedata.com/quote"
TWELVE_DATA_SERIES_URL = "https://api.twelvedata.com/time_series"
DXY_BASE_FACTOR = 50.14348112
DXY_COMPONENT_WEIGHTS: dict[str, tuple[str, float]] = {
    "EUR/USD": ("eurusd", -0.576),
    "USD/JPY": ("usdjpy", 0.136),
    "GBP/USD": ("gbpusd", -0.119),
    "USD/CAD": ("usdcad", 0.091),
    "USD/SEK": ("usdsek", 0.042),
    "USD/CHF": ("usdchf", 0.036),
}


class MacroSourceRateLimited(ValueError):
    """The macro provider refused a read because its rate or credit limit was reached."""


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class TwelveDataMacroProvider:
    provider_name = "twelve_data"

    # Twelve Data is still useful for direct spot-style macro inputs such as gold.
    SYMBOL_MAP: dict[str, str] = {
        "gold_price": "XAU/USD",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or ""

    def supports_indicator(self, indicator_name: str) -> bool:
        return indicator_name in self.SYMBOL_MAP

    def fetch_latest_value(self, indicator_name: str) -> float | None:
        if not self.api_key or not self.supports_indicator(indicator_name):
            return None

        provider_symbol = self.SYMBOL_MAP[indicator_name]
        return self.fetch_quote_value(provider_symbol)

    def fetch_quote_value(self, provider_symbol: str) -> float | None:
        reading = self.fetch_quote_reading(provider_symbol)
        return reading["value"] if reading else None

    def fetch_quote_reading(self, provider_symbol: str) -> dict | None:
        if not self.api_key:
            return None

        response = requests.get(
            TWELVE_DATA_QUOTE_URL,
            params={
                "symbol": provider_symbol,
                "apikey": self.api_key,
            },
            timeout=10,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/137.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            raise ValueError(payload.get("message") or f"Twelve Data quote error for {provider_symbol}")

        raw_value = (
            _float_or_none(payload.get("close"))
            or _float_or_none(payload.get("price"))
            or _float_or_none(payload.get("previous_close"))
        )
        if raw_value is None:
            return None

        observed_at = None
        timestamp = payload.get("timestamp")
        try:
            if timestamp is not None:
                observed_at = datetime.fromtimestamp(float(timestamp), timezone.utc)
            elif payload.get("last_update_at"):
                observed_at = datetime.fromisoformat(
                    str(payload["last_update_at"]).replace("Z", "+00:00")
                ).astimezone(timezone.utc)
        except (TypeError, ValueError, OverflowError):
            observed_at = None
        return {"value": raw_value, "observed_at": observed_at}

    def fetch_daily_history(self, provider_symbol: str, *, limit: int = 100) -> dict[str, float]:
        """Return dated closes from the same provider used for live macro quotes."""
        if not self.api_key:
            return {}
        response = requests.get(
            TWELVE_DATA_SERIES_URL,
            params={"symbol": provider_symbol, "interval": "1day",
                    "outputsize": min(max(limit, 5), 100), "apikey": self.api_key},
            timeout=15,
        )
        if response.status_code == 429:
            raise MacroSourceRateLimited("macro_source_rate_limited")
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") == "error":
            if str(payload.get("code")) == "429":
                raise MacroSourceRateLimited("macro_source_rate_limited")
            raise ValueError(payload.get("message") or "Twelve Data history unavailable")
        history: dict[str, float] = {}
        for item in payload.get("values") or []:
            day = str(item.get("datetime") or "")[:10]
            value = _float_or_none(item.get("close"))
            if day and value is not None and math.isfinite(value):
                history[day] = value
        return history

    def fetch_derived_dxy_history(self, *, limit: int = 100) -> dict[str, float]:
        """Only score days for which all six basket components were measured."""
        components = {
            symbol: self.fetch_daily_history(symbol, limit=limit)
            for symbol in DXY_COMPONENT_WEIGHTS
        }
        if not components or any(not readings for readings in components.values()):
            return {}
        complete_days = set.intersection(*(set(readings) for readings in components.values()))
        history: dict[str, float] = {}
        for day in complete_days:
            value = DXY_BASE_FACTOR
            for symbol, (_, exponent) in DXY_COMPONENT_WEIGHTS.items():
                rate = components[symbol][day]
                if rate <= 0:
                    break
                value *= math.pow(rate, exponent)
            else:
                history[day] = value
        return history

    def fetch_derived_dxy_reading(self) -> dict | None:
        if not self.api_key:
            return None
        weighted_product = DXY_BASE_FACTOR
        observations = []
        for provider_symbol, (_, exponent) in DXY_COMPONENT_WEIGHTS.items():
            reading = self.fetch_quote_reading(provider_symbol)
            if not reading or reading["value"] in (None, 0):
                return None
            weighted_product *= math.pow(float(reading["value"]), exponent)
            if reading.get("observed_at") is not None:
                observations.append(reading["observed_at"])
        return {"value": weighted_product,
                "observed_at": min(observations) if len(observations) == len(DXY_COMPONENT_WEIGHTS) else None}

    def fetch_derived_dxy(self) -> float | None:
        if not self.api_key:
            return None

        weighted_product = DXY_BASE_FACTOR
        for provider_symbol, (_, exponent) in DXY_COMPONENT_WEIGHTS.items():
            quote_value = self.fetch_quote_value(provider_symbol)
            if quote_value in (None, 0):
                return None
            weighted_product *= math.pow(float(quote_value), exponent)

        return weighted_product
