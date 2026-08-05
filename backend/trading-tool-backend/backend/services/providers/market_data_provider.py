from __future__ import annotations

from datetime import datetime
from typing import Protocol

from backend.schemas.market_provider_schema import AssetRecord, OHLCVCandleDTO, PriceSnapshotDTO


class MarketDataProvider(Protocol):
    provider_name: str

    async def fetch_latest_snapshot(self, asset: AssetRecord) -> PriceSnapshotDTO:
        ...

    async def fetch_candles(
        self,
        asset: AssetRecord,
        timeframe: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> list[OHLCVCandleDTO]:
        ...
