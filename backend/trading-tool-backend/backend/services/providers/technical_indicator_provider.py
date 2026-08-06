from __future__ import annotations

from typing import Protocol

from backend.schemas.market_provider_schema import AssetRecord


class TechnicalIndicatorProvider(Protocol):
    provider_name: str

    async def fetch_indicator_value(self, asset: AssetRecord, indicator_name: str) -> float:
        ...
