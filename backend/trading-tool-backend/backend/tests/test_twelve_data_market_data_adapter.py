import asyncio

import pytest

from backend.schemas.market_provider_schema import AssetRecord
from backend.services.providers.twelve_data_market_data_adapter import TwelveDataMarketDataAdapter


def test_twelve_data_quote_without_configuration_is_typed_unavailable():
    adapter = TwelveDataMarketDataAdapter(api_key="")
    asset = AssetRecord(
        symbol="AAPL",
        display_name="Apple Inc.",
        asset_class="equity",
        provider="twelve_data",
        quote_currency="USD",
        primary_provider="twelve_data",
        provider_symbol="AAPL",
    )

    with pytest.raises(ValueError, match="twelve_data_not_configured"):
        asyncio.run(adapter.fetch_latest_snapshot(asset))
