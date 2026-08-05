from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from backend.schemas.market_provider_schema import AssetRecord, OHLCVCandleDTO, PriceSnapshotDTO


def _float_or_none(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


class TwelveDataMarketDataAdapter:
    provider_name = "twelve_data"
    base_url = "https://api.twelvedata.com"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TWELVE_DATA_API_KEY") or ""

    def _params(self, **extra: Any) -> dict[str, Any]:
        params = {"apikey": self.api_key}
        params.update(extra)
        return params

    async def fetch_latest_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO:
        provider_symbol = asset.provider_symbol or asset.symbol
        async with httpx.AsyncClient(timeout=10.0) as client:
            quote_res = await client.get(
                f"{self.base_url}/quote",
                params=self._params(symbol=provider_symbol, interval="1min"),
            )
            quote_res.raise_for_status()
            payload = quote_res.json()

        observed_at = _parse_datetime(payload.get("datetime")) or datetime.now(UTC)
        return PriceSnapshotDTO(
            symbol=asset.symbol,
            provider=self.provider_name,
            provider_symbol=provider_symbol,
            price=_float_or_none(payload.get("close")) or _float_or_none(payload.get("price")),
            open=_float_or_none(payload.get("open")),
            high=_float_or_none(payload.get("high")),
            low=_float_or_none(payload.get("low")),
            previous_close=_float_or_none(payload.get("previous_close")),
            change_absolute=_float_or_none(payload.get("change")),
            change_percent=_float_or_none(payload.get("percent_change")),
            volume=_float_or_none(payload.get("volume")),
            currency=payload.get("currency") or asset.quote_currency,
            exchange=payload.get("exchange") or asset.exchange,
            observed_at=observed_at,
            is_delayed=asset.is_delayed,
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
        provider_symbol = asset.provider_symbol or asset.symbol
        params: dict[str, Any] = self._params(
            symbol=provider_symbol,
            interval=timeframe,
            outputsize=limit or 100,
            order="ASC",
            format="JSON",
        )
        if start_at is not None:
            params["start_date"] = start_at.strftime("%Y-%m-%d %H:%M:%S")
        if end_at is not None:
            params["end_date"] = end_at.strftime("%Y-%m-%d %H:%M:%S")

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self.base_url}/time_series", params=params)
            response.raise_for_status()
            payload = response.json()

        values = payload.get("values") or []
        candles: list[OHLCVCandleDTO] = []
        for item in values:
            period_start = _parse_datetime(item.get("datetime"))
            if period_start is None:
                continue
            candles.append(
                OHLCVCandleDTO(
                    symbol=asset.symbol,
                    provider=self.provider_name,
                    provider_symbol=provider_symbol,
                    timeframe=timeframe,
                    open=float(item["open"]),
                    high=float(item["high"]),
                    low=float(item["low"]),
                    close=float(item["close"]),
                    volume=_float_or_none(item.get("volume")),
                    period_start=period_start,
                    raw_payload=item,
                )
            )
        return candles
