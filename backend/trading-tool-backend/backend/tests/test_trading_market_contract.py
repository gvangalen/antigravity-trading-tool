import asyncio
from datetime import datetime, timezone

import pytest
import httpx

from backend.schemas.market_provider_schema import PriceSnapshotDTO
from backend.services.market_data_ingestion_service import MarketDataIngestionService
from backend.utils.market_interpreter import normalize_market_value_with_history
from backend.utils.scoring_utils import generate_scores_db

from backend.services.trading_market_service import (
    MarketUnavailable,
    TradingMarket,
    TradingMarketService,
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


def test_market_choices_show_only_exact_verified_pairs_without_writing(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            assert url.endswith("/exchangeInfo")
            symbol = params["symbol"]
            if symbol == "BTCEUR":
                return httpx.Response(200, json=_exchange_info(),
                                      request=httpx.Request("GET", url))
            return httpx.Response(400, json={"code": -1121},
                                  request=httpx.Request("GET", url))

    monkeypatch.setattr("backend.services.trading_market_service.httpx.AsyncClient",
                        lambda **_kwargs: Client())
    session = _FakeSession()
    choices = asyncio.run(TradingMarketService(session).inspect_crypto_quotes("btc"))
    assert choices == [
        {"pair": "BTC/EUR", "quote_currency": "EUR", "status": "available",
         "venue": "BINANCE", "provider_symbol": "BTCEUR",
         "tradingview_symbol": "BINANCE:BTCEUR"},
        {"pair": "BTC/USDT", "quote_currency": "USDT", "status": "unavailable"},
    ]
    assert session.rows == []


def test_market_choice_provider_outage_is_not_reported_as_unsupported(monkeypatch):
    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, *, params):
            raise httpx.ConnectError("offline", request=httpx.Request("GET", url))

    monkeypatch.setattr("backend.services.trading_market_service.httpx.AsyncClient",
                        lambda **_kwargs: Client())
    choices = asyncio.run(TradingMarketService(_FakeSession()).inspect_crypto_quotes("btc"))
    assert [choice["status"] for choice in choices] == [
        "verification_unavailable", "verification_unavailable"]


def test_pair_scoring_does_not_consume_legacy_symbol_indicator_configuration(monkeypatch):
    class Cursor:
        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchall(self):
            return []

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

        def close(self):
            pass

    connection = Connection()
    monkeypatch.setattr("backend.utils.scoring_utils.get_db_connection", lambda: connection)
    result = generate_scores_db("market", user_id=9, symbol="BTC", market_id=73)
    assert result["source_status"] == "missing_configuration"
    assert len(connection.cursor_instance.calls) == 1
    sql, params = connection.cursor_instance.calls[0]
    assert "market_id = %s" in sql
    assert params == (9, "market", "BTC", 73)


def test_pair_market_history_is_partitioned_from_other_quote_and_legacy_rows():
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql, params):
            self.sql, self.params = sql, params

        def fetchall(self):
            return [(100,), (110,), (120,), (130,), (140,)]

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()

        def cursor(self):
            return self.cursor_instance

    connection = Connection()
    normalized = normalize_market_value_with_history(
        connection, "BTC", "price", 120, market_id=73)
    assert normalized == 50
    assert "market_id = %s" in connection.cursor_instance.sql
    assert connection.cursor_instance.params == (73,)


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
