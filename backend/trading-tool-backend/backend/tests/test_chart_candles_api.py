import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import asset_catalog_api
from backend.schemas.market_provider_schema import OHLCVCandleDTO


class _Result:
    def __init__(self, value):
        self.value = value

    def scalars(self):
        return self

    def first(self):
        return self.value


class _Session:
    def __init__(self, market=None, catalog=None):
        self.rows = iter((market, catalog))

    async def execute(self, _query):
        return _Result(next(self.rows))


@pytest.mark.parametrize("quote,provider_symbol,chart_interval,provider_interval", [
    ("EUR", "SOLEUR", "D", "1d"),
    ("USDT", "SOLUSDT", "D", "1d"),
    ("USDT", "SOLUSDT", "3M", "3M"),
])
def test_chart_candles_use_exact_verified_pair(monkeypatch, quote, provider_symbol,
                                                chart_interval, provider_interval):
    market = SimpleNamespace(asset_symbol="SOL", provider="binance", provider_symbol=provider_symbol,
                             quote_currency=quote, venue="BINANCE")
    catalog = SimpleNamespace(display_name="Solana", asset_class="crypto", timezone="UTC")
    seen = {}

    class Provider:
        provider_name = "binance"

        async def fetch_candles(self, asset, interval, limit):
            seen.update(provider_symbol=asset.provider_symbol, interval=interval, limit=limit)
            return [OHLCVCandleDTO(symbol="SOL", provider="binance", provider_symbol=provider_symbol,
                    timeframe="1d", open=100, high=102, low=99, close=101, volume=50,
                    period_start=datetime(2026, 11, 1, tzinfo=timezone.utc))]

    class Registry:
        def resolve_for_asset(self, asset):
            return Provider()

    monkeypatch.setattr(asset_catalog_api, "MarketDataProviderRegistry", Registry)
    result = asyncio.run(asset_catalog_api.get_verified_chart_candles(
        tradingview_symbol=f"BINANCE:{provider_symbol}", interval=chart_interval,
        current_user={"id": 7}, session=_Session(market, catalog)))
    assert seen == {"provider_symbol": provider_symbol, "interval": provider_interval, "limit": 220}
    assert result["symbol"] == f"BINANCE:{provider_symbol}"
    assert result["quote_currency"] == quote
    assert result["candles"][0]["close"] == 101


def test_chart_candles_reject_unverified_symbol():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(asset_catalog_api.get_verified_chart_candles(
            tradingview_symbol="BINANCE:UNKNOWNUSDT", interval="D",
            current_user={"id": 7}, session=_Session(None, None)))
    assert exc.value.status_code == 404


def test_stock_quarter_chart_aggregates_monthly_candles(monkeypatch):
    catalog = SimpleNamespace(symbol="AAPL", display_name="Apple", asset_class="stock",
                              primary_provider="twelve_data", provider="twelve_data",
                              provider_symbol="AAPL", quote_currency="USD", exchange="NASDAQ",
                              timezone="America/New_York")
    monthly = [OHLCVCandleDTO(symbol="AAPL", provider="twelve_data", provider_symbol="AAPL",
               timeframe="1month", open=open_price, high=high, low=low, close=close,
               volume=10, period_start=datetime(2026, month, 1, tzinfo=timezone.utc))
               for month, open_price, high, low, close in [
                   (1, 100, 110, 90, 105), (2, 105, 115, 95, 108),
                   (3, 108, 120, 99, 119), (4, 119, 122, 101, 111)]]

    class Provider:
        provider_name = "twelve_data"

        async def fetch_candles(self, asset, interval, limit):
            assert asset.provider_symbol == "AAPL"
            assert interval == "1month"
            return monthly

    class Registry:
        def resolve_for_asset(self, asset):
            return Provider()

    monkeypatch.setattr(asset_catalog_api, "MarketDataProviderRegistry", Registry)
    result = asyncio.run(asset_catalog_api.get_verified_chart_candles(
        tradingview_symbol="NASDAQ:AAPL", interval="3M", current_user={"id": 7},
        session=_Session(None, catalog)))
    assert len(result["candles"]) == 2
    assert result["candles"][0]["open"] == 100
    assert result["candles"][0]["high"] == 120
    assert result["candles"][0]["close"] == 119
    assert result["candles"][0]["volume"] == 30
