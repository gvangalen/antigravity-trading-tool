from __future__ import annotations

import os

import httpx

from backend.schemas.market_provider_schema import AssetRecord


class TwelveDataTechnicalIndicatorAdapter:
    provider_name = "twelve_data"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or ""
        self._quote_cache: dict[str, dict] = {}

    async def fetch_indicator_value(self, asset: AssetRecord, indicator_name: str) -> float:
        normalized = str(indicator_name or "").strip().lower()
        symbol = self._provider_symbol(asset)

        if normalized == "rsi":
            payload = await self._get(
                "/rsi",
                symbol=symbol,
                interval="1day",
                time_period=14,
                outputsize=1,
            )
            return float(payload["values"][0]["rsi"])

        if normalized == "ma_50":
            return await self._moving_average_ratio(symbol, endpoint="/sma", period=50, field="sma")

        if normalized == "ma_200":
            return await self._moving_average_ratio(symbol, endpoint="/sma", period=200, field="sma")

        if normalized == "ema_20_gap_pct":
            return await self._ema_gap_pct(symbol, period=20)

        if normalized == "ema_50_gap_pct":
            return await self._ema_gap_pct(symbol, period=50)

        if normalized == "macd_hist_pct":
            quote_payload = await self._get_quote(symbol)
            macd_payload = await self._get(
                "/macd",
                symbol=symbol,
                interval="1day",
                fast_period=12,
                slow_period=26,
                signal_period=9,
                outputsize=1,
            )
            close = float(quote_payload["close"])
            hist = float(macd_payload["values"][0]["macd_hist"])
            if close == 0:
                return 0.0
            return (hist / close) * 100.0

        if normalized == "atr_pct":
            quote_payload = await self._get_quote(symbol)
            atr_payload = await self._get(
                "/atr",
                symbol=symbol,
                interval="1day",
                time_period=14,
                outputsize=1,
            )
            close = float(quote_payload["close"])
            atr = float(atr_payload["values"][0]["atr"])
            if close == 0:
                return 0.0
            return (atr / close) * 100.0

        if normalized == "adx":
            payload = await self._get(
                "/adx",
                symbol=symbol,
                interval="1day",
                time_period=14,
                outputsize=1,
            )
            return float(payload["values"][0]["adx"])

        raise ValueError(f"Unsupported Twelve Data technical indicator: {indicator_name}")

    def _provider_symbol(self, asset: AssetRecord) -> str:
        provider_symbol = str(asset.provider_symbol or asset.symbol or "").strip().upper()
        if asset.asset_class == "crypto":
            for quote in ("USDT", "USDC", "USD", "BUSD", "FDUSD", "EUR"):
                if provider_symbol.endswith(quote) and len(provider_symbol) > len(quote):
                    base = provider_symbol[: -len(quote)]
                    return f"{base}/{quote}"
        return provider_symbol

    async def _moving_average_ratio(self, symbol: str, *, endpoint: str, period: int, field: str) -> float:
        quote_payload = await self._get_quote(symbol)
        ma_payload = await self._get(
            endpoint,
            symbol=symbol,
            interval="1day",
            time_period=period,
            outputsize=1,
        )
        close = float(quote_payload["close"])
        average = float(ma_payload["values"][0][field])
        if average == 0:
            return 0.0
        return close / average

    async def _ema_gap_pct(self, symbol: str, *, period: int) -> float:
        quote_payload = await self._get_quote(symbol)
        ema_payload = await self._get(
            "/ema",
            symbol=symbol,
            interval="1day",
            time_period=period,
            outputsize=1,
        )
        close = float(quote_payload["close"])
        ema = float(ema_payload["values"][0]["ema"])
        if ema == 0:
            return 0.0
        return ((close - ema) / ema) * 100.0

    async def _get_quote(self, symbol: str) -> dict:
        if symbol not in self._quote_cache:
            self._quote_cache[symbol] = await self._get("/quote", symbol=symbol)
        return self._quote_cache[symbol]

    async def _get(self, endpoint: str, **params):
        query = {"apikey": self.api_key, **params}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}{endpoint}", params=query)
            response.raise_for_status()
            return response.json()
