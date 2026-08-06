from __future__ import annotations

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.binance_market_data_adapter import BinanceMarketDataAdapter
from backend.services.providers.market_data_provider import MarketDataProvider
from backend.services.providers.twelve_data_market_data_adapter import TwelveDataMarketDataAdapter


class MarketDataProviderRegistry:
    def __init__(self):
        self._providers: dict[str, MarketDataProvider] = {
            "binance": BinanceMarketDataAdapter(),
            "twelve_data": TwelveDataMarketDataAdapter(),
        }

    def get_provider(self, provider_name: str | None) -> MarketDataProvider:
        normalized = str(provider_name or "").strip().lower()
        if normalized in self._providers:
            return self._providers[normalized]
        raise KeyError(f"Unknown market data provider: {provider_name}")

    def resolve_for_asset(self, asset: AssetRecord) -> MarketDataProvider:
        primary = str(asset.primary_provider or asset.provider or "").strip().lower()
        if primary and primary not in {"seed", "default", "manual", "database", "fallback"}:
            return self.get_provider(primary)

        if asset.asset_class == "crypto":
            return self.get_provider("binance")

        return self.get_provider("twelve_data")
