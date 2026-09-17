import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.services.market_data_service import MarketDataService


def test_market_indicator_catalog_is_available_for_an_empty_database():
    service = MarketDataService(AsyncMock())
    service.repository = SimpleNamespace(get_global_indicators=AsyncMock(return_value=[]))

    rows = asyncio.run(service.get_global_indicators())

    assert {row["name"] for row in rows} == {"price", "volume", "change_24h"}


def test_market_indicator_catalog_preserves_database_extensions_without_overriding_canonical_labels():
    service = MarketDataService(AsyncMock())
    service.repository = SimpleNamespace(
        get_global_indicators=AsyncMock(
            return_value=[
                SimpleNamespace(name="volume", display_name="Legacy Volume"),
                SimpleNamespace(name="volatility", display_name="Volatility"),
            ]
        )
    )

    rows = asyncio.run(service.get_global_indicators())
    by_name = {row["name"]: row["display_name"] for row in rows}

    assert by_name["volume"] == "Volume"
    assert by_name["volatility"] == "Volatility"
