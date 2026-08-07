from __future__ import annotations

import os
from typing import Any

import requests


TWELVE_DATA_QUOTE_URL = "https://api.twelvedata.com/quote"


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class TwelveDataMacroProvider:
    provider_name = "twelve_data"

    # Only map symbols we already validated internally or can support safely
    # with our current asset catalog routing.
    SYMBOL_MAP: dict[str, str] = {
        "sp500": "SPX",
        "vix": "VIX",
        "dxy": "DXY",
        "gold_price": "GLD",
    }

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or ""

    def supports_indicator(self, indicator_name: str) -> bool:
        return indicator_name in self.SYMBOL_MAP

    def fetch_latest_value(self, indicator_name: str) -> float | None:
        if not self.api_key or not self.supports_indicator(indicator_name):
            return None

        provider_symbol = self.SYMBOL_MAP[indicator_name]
        response = requests.get(
            TWELVE_DATA_QUOTE_URL,
            params={
                "symbol": provider_symbol,
                "apikey": self.api_key,
                "interval": "1min",
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

        return _float_or_none(payload.get("close")) or _float_or_none(payload.get("price")) or _float_or_none(payload.get("previous_close"))
