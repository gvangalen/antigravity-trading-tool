from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx

from backend.schemas.market_provider_schema import AssetRecord, OHLCVCandleDTO, PriceSnapshotDTO


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


class BinanceMarketDataAdapter:
    provider_name = "binance"
    base_url = "https://api.binance.com/api/v3"

    async def fetch_latest_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO:
        provider_symbol = asset.provider_symbol or f"{asset.symbol}USDT"
        url = f"{self.base_url}/ticker/24hr"
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params={"symbol": provider_symbol})
            response.raise_for_status()
            payload = response.json()

        return PriceSnapshotDTO(
            symbol=asset.symbol,
            provider=self.provider_name,
            provider_symbol=provider_symbol,
            price=_float_or_none(payload.get("lastPrice")),
            open=_float_or_none(payload.get("openPrice")),
            high=_float_or_none(payload.get("highPrice")),
            low=_float_or_none(payload.get("lowPrice")),
            previous_close=_float_or_none(payload.get("prevClosePrice")),
            change_absolute=_float_or_none(payload.get("priceChange")),
            change_percent=_float_or_none(payload.get("priceChangePercent")),
            volume=_float_or_none(payload.get("quoteVolume")),
            currency=asset.quote_currency,
            exchange=asset.exchange or "BINANCE",
            observed_at=datetime.now(UTC),
            is_delayed=False,
            raw_payload=payload,
        )

    async def fetch_candles(
        self,
        asset: AssetRecord,
        timeframe: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVCandleDTO]:
        provider_symbol = asset.provider_symbol or f"{asset.symbol}USDT"
        params: dict[str, Any] = {
            "symbol": provider_symbol,
            "interval": timeframe,
            "limit": limit or 100,
        }
        if start_at is not None:
            params["startTime"] = int(start_at.timestamp() * 1000)
        if end_at is not None:
            params["endTime"] = int(end_at.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self.base_url}/klines", params=params)
            response.raise_for_status()
            payload = response.json()

        candles: list[OHLCVCandleDTO] = []
        for item in payload:
            period_start = datetime.fromtimestamp(int(item[0]) / 1000, UTC)
            period_end = datetime.fromtimestamp(int(item[6]) / 1000, UTC)
            candles.append(
                OHLCVCandleDTO(
                    symbol=asset.symbol,
                    provider=self.provider_name,
                    provider_symbol=provider_symbol,
                    timeframe=timeframe,
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=_float_or_none(item[7]),
                    period_start=period_start,
                    period_end=period_end,
                    raw_payload={"kline": item},
                )
            )
        return candles
