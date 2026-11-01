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


@pytest.mark.parametrize("quote,provider_symbol", [("EUR", "SOLEUR"), ("USDT", "SOLUSDT")])
def test_chart_candles_use_exact_verified_pair(monkeypatch, quote, provider_symbol):
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
        tradingview_symbol=f"BINANCE:{provider_symbol}", interval="D",
        current_user={"id": 7}, session=_Session(market, catalog)))
    assert seen == {"provider_symbol": provider_symbol, "interval": "1d", "limit": 220}
    assert result["symbol"] == f"BINANCE:{provider_symbol}"
    assert result["quote_currency"] == quote
    assert result["candles"][0]["close"] == 101


def test_chart_candles_reject_unverified_symbol():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(asset_catalog_api.get_verified_chart_candles(
            tradingview_symbol="BINANCE:UNKNOWNUSDT", interval="D",
            current_user={"id": 7}, session=_Session(None, None)))
    assert exc.value.status_code == 404
