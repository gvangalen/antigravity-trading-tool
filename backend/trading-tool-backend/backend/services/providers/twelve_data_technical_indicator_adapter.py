from __future__ import annotations

import os

import httpx

from backend.schemas.market_provider_schema import AssetRecord
from backend.utils.technical_interpreter import calculate_rsi


class TwelveDataTechnicalIndicatorAdapter:
    provider_name = "twelve_data"
    base_url = "https://api.twelvedata.com"
    binance_base_url = "https://api.binance.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or ""
        self._quote_cache: dict[str, dict] = {}
        self._binance_candle_cache: dict[str, list[dict[str, float]]] = {}

    async def fetch_indicator_value(self, asset: AssetRecord, indicator_name: str) -> float:
        normalized = str(indicator_name or "").strip().lower()
        if asset.asset_class == "crypto":
            fallback = await self._fetch_without_api_key(asset, normalized)
            if fallback is not None:
                return fallback

        if not self.api_key:
            fallback = await self._fetch_without_api_key(asset, normalized)
            if fallback is not None:
                return fallback

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

    async def _fetch_without_api_key(self, asset: AssetRecord, indicator_name: str) -> float | None:
        if asset.asset_class != "crypto":
            raise ValueError(
                f"TWELVE_DATA_API_KEY ontbreekt op de backend; '{indicator_name}' kan zonder key alleen voor crypto worden berekend."
            )

        symbol = self._binance_symbol(asset)
        candles = await self._get_binance_candles(symbol)
        if not candles:
            raise ValueError(f"Geen candles beschikbaar voor '{asset.symbol}' via Binance fallback.")

        closes = [candle["close"] for candle in candles]
        highs = [candle["high"] for candle in candles]
        lows = [candle["low"] for candle in candles]
        close = closes[-1]

        if indicator_name == "rsi":
            value = calculate_rsi(closes, period=14)
            if value is None:
                raise ValueError(f"Onvoldoende candlehistorie voor RSI ({asset.symbol}).")
            return float(value)

        if indicator_name == "ma_50":
            return self._moving_average_ratio_from_closes(closes, period=50)

        if indicator_name == "ma_200":
            return self._moving_average_ratio_from_closes(closes, period=200)

        if indicator_name == "ema_20_gap_pct":
            return self._ema_gap_pct_from_closes(closes, period=20)

        if indicator_name == "ema_50_gap_pct":
            return self._ema_gap_pct_from_closes(closes, period=50)

        if indicator_name == "macd_hist_pct":
            macd_hist = self._macd_histogram(closes)
            if close == 0:
                return 0.0
            return (macd_hist / close) * 100.0

        if indicator_name == "atr_pct":
            atr = self._atr(highs, lows, closes, period=14)
            if close == 0:
                return 0.0
            return (atr / close) * 100.0

        if indicator_name == "adx":
            return self._adx(highs, lows, closes, period=14)

        return None

    def _provider_symbol(self, asset: AssetRecord) -> str:
        provider_symbol = str(asset.provider_symbol or asset.symbol or "").strip().upper()
        if asset.asset_class == "crypto":
            for quote in ("USDT", "USDC", "BUSD", "FDUSD"):
                if provider_symbol.endswith(quote) and len(provider_symbol) > len(quote):
                    base = provider_symbol[: -len(quote)]
                    return f"{base}/USD"
            for quote in ("USD", "EUR"):
                if provider_symbol.endswith(quote) and len(provider_symbol) > len(quote):
                    base = provider_symbol[: -len(quote)]
                    return f"{base}/{quote}"
        return provider_symbol

    def _binance_symbol(self, asset: AssetRecord) -> str:
        provider_symbol = str(asset.provider_symbol or asset.symbol or "").strip().upper()
        return provider_symbol.replace("/", "")

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

    async def _get_binance_candles(self, symbol: str, *, limit: int = 300) -> list[dict[str, float]]:
        if symbol not in self._binance_candle_cache:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(
                    f"{self.binance_base_url}/api/v3/klines",
                    params={"symbol": symbol, "interval": "1d", "limit": limit},
                )
                response.raise_for_status()
                rows = response.json()
            self._binance_candle_cache[symbol] = [
                {
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                }
                for row in rows
            ]
        return self._binance_candle_cache[symbol]

    async def _get(self, endpoint: str, **params):
        query = {"apikey": self.api_key, **params}
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}{endpoint}", params=query)
            response.raise_for_status()
            return response.json()

    @staticmethod
    def _moving_average_ratio_from_closes(closes: list[float], *, period: int) -> float:
        if len(closes) < period:
            raise ValueError(f"Onvoldoende candlehistorie voor MA{period}.")
        average = sum(closes[-period:]) / period
        if average == 0:
            return 0.0
        return closes[-1] / average

    @staticmethod
    def _ema(values: list[float], period: int) -> list[float]:
        if len(values) < period:
            raise ValueError(f"Onvoldoende candlehistorie voor EMA{period}.")
        multiplier = 2 / (period + 1)
        ema_values = [sum(values[:period]) / period]
        for value in values[period:]:
            ema_values.append((value - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values

    def _ema_gap_pct_from_closes(self, closes: list[float], *, period: int) -> float:
        ema_series = self._ema(closes, period)
        ema_value = ema_series[-1]
        if ema_value == 0:
            return 0.0
        return ((closes[-1] - ema_value) / ema_value) * 100.0

    def _macd_histogram(self, closes: list[float]) -> float:
        ema12 = self._ema(closes, 12)
        ema26 = self._ema(closes, 26)
        aligned_ema12 = ema12[-len(ema26):]
        macd_line = [fast - slow for fast, slow in zip(aligned_ema12, ema26)]
        signal_line = self._ema(macd_line, 9)
        macd_tail = macd_line[-len(signal_line):]
        return macd_tail[-1] - signal_line[-1]

    @staticmethod
    def _true_ranges(highs: list[float], lows: list[float], closes: list[float]) -> list[float]:
        trs: list[float] = []
        for index in range(1, len(closes)):
            tr = max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            )
            trs.append(tr)
        return trs

    def _atr(self, highs: list[float], lows: list[float], closes: list[float], *, period: int) -> float:
        trs = self._true_ranges(highs, lows, closes)
        if len(trs) < period:
            raise ValueError(f"Onvoldoende candlehistorie voor ATR{period}.")
        atr = sum(trs[:period]) / period
        for tr in trs[period:]:
            atr = ((atr * (period - 1)) + tr) / period
        return atr

    def _adx(self, highs: list[float], lows: list[float], closes: list[float], *, period: int) -> float:
        if len(closes) <= period * 2:
            raise ValueError(f"Onvoldoende candlehistorie voor ADX{period}.")

        trs: list[float] = []
        plus_dm: list[float] = []
        minus_dm: list[float] = []

        for index in range(1, len(closes)):
            up_move = highs[index] - highs[index - 1]
            down_move = lows[index - 1] - lows[index]
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
            trs.append(
                max(
                    highs[index] - lows[index],
                    abs(highs[index] - closes[index - 1]),
                    abs(lows[index] - closes[index - 1]),
                )
            )

        atr = sum(trs[:period])
        plus = sum(plus_dm[:period])
        minus = sum(minus_dm[:period])

        dxs: list[float] = []
        for index in range(period, len(trs)):
            atr = atr - (atr / period) + trs[index]
            plus = plus - (plus / period) + plus_dm[index]
            minus = minus - (minus / period) + minus_dm[index]
            if atr == 0:
                dxs.append(0.0)
                continue
            plus_di = (plus / atr) * 100.0
            minus_di = (minus / atr) * 100.0
            denominator = plus_di + minus_di
            if denominator == 0:
                dxs.append(0.0)
            else:
                dxs.append((abs(plus_di - minus_di) / denominator) * 100.0)

        if len(dxs) < period:
            raise ValueError(f"Onvoldoende candlehistorie voor ADX{period}.")

        adx = sum(dxs[:period]) / period
        for dx in dxs[period:]:
            adx = ((adx * (period - 1)) + dx) / period
        return adx
