from __future__ import annotations

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.technical_indicator_provider import TechnicalIndicatorProvider
from backend.services.providers.twelve_data_technical_indicator_adapter import (
    TwelveDataTechnicalIndicatorAdapter,
)


class TechnicalIndicatorProviderRegistry:
    def __init__(self):
        self._providers: dict[str, TechnicalIndicatorProvider] = {
            "twelve_data": TwelveDataTechnicalIndicatorAdapter(),
        }
        self._supported_indicators = {
            "rsi",
            "ma_50",
            "ma_200",
            "ema_20_gap_pct",
            "ema_50_gap_pct",
            "macd_hist_pct",
            "atr_pct",
            "adx",
        }

    def resolve_for_asset(self, asset: AssetRecord, indicator_name: str) -> TechnicalIndicatorProvider | None:
        normalized = str(indicator_name or "").strip().lower()
        if normalized not in self._supported_indicators:
            return None
        if asset.asset_class in {"crypto", "stock", "etf", "index"}:
            return self._providers["twelve_data"]
        return None
