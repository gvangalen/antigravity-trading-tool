import asyncio
from datetime import datetime, timezone

import pytest

from backend.schemas.market_provider_schema import PriceSnapshotDTO
from backend.services.market_data_ingestion_service import MarketDataIngestionService

from backend.services.trading_market_service import (
    MarketUnavailable,
    TradingMarket,
    normalize_pair,
    verify_binance_pair,
)


def _exchange_info(base="BTC", quote="EUR", **changes):
    row = {"symbol": f"{base}{quote}", "baseAsset": base,
           "quoteAsset": quote, "status": "TRADING",
           "isSpotTradingAllowed": True}
    row.update(changes)
    return {"symbols": [row]}


def test_exact_pair_is_normalized_and_verified():
    assert normalize_pair(" btc ", "eur") == ("BTC", "EUR")
    assert verify_binance_pair(_exchange_info(), "BTC", "EUR") == "BTCEUR"


@pytest.mark.parametrize("payload", [
    _exchange_info(quote="USDT"),
    _exchange_info(status="BREAK"),
    _exchange_info(isSpotTradingAllowed=False),
    {"symbols": []},
    {"symbols": [_exchange_info()["symbols"][0], _exchange_info()["symbols"][0]]},
])
def test_pair_verification_never_substitutes_a_different_market(payload):
    with pytest.raises(MarketUnavailable):
        verify_binance_pair(payload, "BTC", "EUR")


def test_pair_does_not_treat_usdt_as_usd_or_eur():
    with pytest.raises(MarketUnavailable):
        verify_binance_pair(_exchange_info(quote="USDT"), "BTC", "USD")
    with pytest.raises(MarketUnavailable):
        normalize_pair("ETH", "ETH")


class _FakeSession:
    def __init__(self):
        self.rows = []

    def add(self, row):
        self.rows.append(row)

    async def flush(self):
        pass

    async def commit(self):
        pass


class _FakeCatalog:
    async def get_asset(self, symbol):
        return {"symbol": symbol, "display_name": "Bitcoin", "asset_class": "crypto",
                "provider": "binance", "primary_provider": "binance",
                "provider_symbol": "BTCUSDT", "quote_currency": "USDT"}


def _trading_market(quote="EUR"):
    return TradingMarket(7, "BTC", quote, "BINANCE", "binance", f"BTC{quote}",
                         f"BINANCE:BTC{quote}", datetime.now(timezone.utc))


def _snapshot(quote="EUR", provider_symbol=None):
    return PriceSnapshotDTO(symbol="BTC", provider="binance",
                            provider_symbol=provider_symbol or f"BTC{quote}",
                            price=70000, currency=quote,
                            observed_at=datetime.now(timezone.utc))


def test_exact_market_ingestion_uses_selected_pair_even_when_catalog_defaults_to_usdt():
    session = _FakeSession()
    service = MarketDataIngestionService(session)
    service.asset_catalog_service = _FakeCatalog()
    observed = {}

    async def fetch(asset):
        observed["quote"] = asset.quote_currency
        observed["provider_symbol"] = asset.provider_symbol
        return _snapshot()

    service._fetch_snapshot = fetch
    result = asyncio.run(service.ingest_exact_market_snapshot(_trading_market(), commit=False))
    assert observed == {"quote": "EUR", "provider_symbol": "BTCEUR"}
    assert result["pair"] == "BTC/EUR"
    assert len(session.rows) == 1
    assert session.rows[0].market_id == 7
    assert session.rows[0].quote_currency == "EUR"


def test_exact_market_ingestion_rejects_wrong_provider_symbol_without_writing():
    session = _FakeSession()
    service = MarketDataIngestionService(session)
    service.asset_catalog_service = _FakeCatalog()

    async def fetch(_asset):
        return _snapshot("EUR", provider_symbol="BTCUSDT")

    service._fetch_snapshot = fetch
    with pytest.raises(ValueError, match="market_provider_symbol_mismatch"):
        asyncio.run(service.ingest_exact_market_snapshot(_trading_market()))
    assert session.rows == []
