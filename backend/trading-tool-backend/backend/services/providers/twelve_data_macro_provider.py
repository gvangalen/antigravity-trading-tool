from __future__ import annotations

import os
import math
from typing import Any

import requests


TWELVE_DATA_QUOTE_URL = "https://api.twelvedata.com/quote"
DXY_BASE_FACTOR = 50.14348112
DXY_COMPONENT_WEIGHTS: dict[str, tuple[str, float]] = {
    "EUR/USD": ("eurusd", -0.576),
    "USD/JPY": ("usdjpy", 0.136),
    "GBP/USD": ("gbpusd", -0.119),
    "USD/CAD": ("usdcad", 0.091),
    "USD/SEK": ("usdsek", 0.042),
    "USD/CHF": ("usdchf", 0.036),
}


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

        return raw_value

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
