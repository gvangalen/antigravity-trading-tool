import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import asset_catalog_api
from backend.services.trading_market_service import MarketUnavailable


class _Session:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def test_selected_pair_without_a_setup_is_registered_and_read_exactly(monkeypatch):
    session = _Session()
    market = SimpleNamespace(id=73, pair="ETH/EUR", quote_currency="EUR",
                             provider_symbol="ETHEUR", tradingview_symbol="BINANCE:ETHEUR")
    calls = []

    class Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, symbol):
            assert symbol == "ETH"
            return {"asset_class": "crypto"}

    class Markets:
        def __init__(self, _session):
            pass

        async def resolve(self, base, quote):
            calls.append((base, quote))
            return market

    class Repository:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, market_id):
            assert market_id == 73
            return None

    class Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_exact_market_snapshot(self, selected):
            assert selected is market
            calls.append((selected.pair, "snapshot"))
            return {"market_id": 73, "observed_at": datetime.now(timezone.utc).isoformat()}

    monkeypatch.setattr(asset_catalog_api, "AssetCatalogService", Catalog)
    monkeypatch.setattr(asset_catalog_api, "TradingMarketService", Markets)
    monkeypatch.setattr(asset_catalog_api, "MarketDataRepository", Repository)
    monkeypatch.setattr(asset_catalog_api, "MarketDataIngestionService", Ingestion)

    result = asyncio.run(asset_catalog_api.select_crypto_trading_market(
        "eth", "eur", current_user={"id": 8}, session=session,
    ))
    assert result["pair"] == "ETH/EUR"
    assert result["tradingview_symbol"] == "BINANCE:ETHEUR"
    assert result["snapshot_status"] == "available"
    assert calls == [("ETH", "EUR"), ("ETH/EUR", "snapshot")]
    assert session.commits == 1


def test_selection_returns_owner_scoped_exact_workspace_in_same_request(monkeypatch):
    session = _Session()
    market = SimpleNamespace(id=81, pair="SOL/EUR", quote_currency="EUR",
                             provider_symbol="SOLEUR", tradingview_symbol="BINANCE:SOLEUR")

    class Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, symbol):
            assert symbol == "SOL"
            return {"asset_class": "crypto"}

    class Markets:
        def __init__(self, _session):
            pass

        async def resolve(self, base, quote):
            assert (base, quote) == ("SOL", "EUR")
            return market

    class Repository:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, market_id):
            assert market_id == 81
            return SimpleNamespace(source_observed_at=datetime.now(timezone.utc))

    class Workspace:
        def __init__(self, workspace_session):
            assert workspace_session is session

        async def get(self, user_id, symbol, quote, *, periods, watchlist_symbols):
            assert (user_id, symbol, quote) == (8, "SOL", "EUR")
            assert periods == {"market": "week", "macro": "day", "technical": "day"}
            assert watchlist_symbols == ["BTC", "ETH"]
            return {"symbol": symbol, "pair": f"{symbol}/{quote}", "market_id": 81,
                    "quote": {"price": None, "status": "insufficient_data"}}

    monkeypatch.setattr(asset_catalog_api, "AssetCatalogService", Catalog)
    monkeypatch.setattr(asset_catalog_api, "TradingMarketService", Markets)
    monkeypatch.setattr(asset_catalog_api, "MarketDataRepository", Repository)
    monkeypatch.setattr(asset_catalog_api, "ExactMarketWorkspaceService", Workspace)
    result = asyncio.run(asset_catalog_api.select_crypto_trading_market(
        "sol", "eur", current_user={"id": 8}, session=session,
        include_workspace=True, market_period="week", watchlist_symbols="BTC,ETH",
    ))
    assert result["workspace"]["pair"] == "SOL/EUR"
    assert result["workspace"]["quote"]["price"] is None
    assert session.commits == 1


def test_unverified_pair_never_uses_another_quote(monkeypatch):
    session = _Session()

    class Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, _symbol):
            return {"asset_class": "crypto"}

    class Markets:
        def __init__(self, _session):
            pass

        async def resolve(self, base, quote):
            assert (base, quote) == ("ETH", "EUR")
            raise MarketUnavailable("ETH/EUR is niet geverifieerd")

    monkeypatch.setattr(asset_catalog_api, "AssetCatalogService", Catalog)
    monkeypatch.setattr(asset_catalog_api, "TradingMarketService", Markets)
    with pytest.raises(HTTPException) as error:
        asyncio.run(asset_catalog_api.select_crypto_trading_market(
            "ETH", "EUR", current_user={"id": 8}, session=session,
        ))
    assert error.value.status_code == 422
    assert session.commits == 0


def test_existing_fresh_snapshot_does_not_requery_the_provider(monkeypatch):
    session = _Session()
    market = SimpleNamespace(id=74, pair="ETH/USDT", quote_currency="USDT",
                             provider_symbol="ETHUSDT", tradingview_symbol="BINANCE:ETHUSDT")

    class Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, _symbol):
            return {"asset_class": "crypto"}

    class Markets:
        def __init__(self, _session):
            pass

        async def resolve(self, _base, _quote):
            return market

    class Repository:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, _market_id):
            return SimpleNamespace(source_observed_at=datetime.now(timezone.utc))

    monkeypatch.setattr(asset_catalog_api, "AssetCatalogService", Catalog)
    monkeypatch.setattr(asset_catalog_api, "TradingMarketService", Markets)
    monkeypatch.setattr(asset_catalog_api, "MarketDataRepository", Repository)
    monkeypatch.setattr(asset_catalog_api, "MarketDataIngestionService",
                        lambda _session: (_ for _ in ()).throw(AssertionError("unexpected provider call")))
    result = asyncio.run(asset_catalog_api.select_crypto_trading_market(
        "ETH", "USDT", current_user={"id": 8}, session=session,
    ))
    assert result["pair"] == "ETH/USDT"
    assert result["snapshot_status"] == "available"


def test_provider_reply_without_source_moment_stays_pending(monkeypatch):
    session = _Session()
    market = SimpleNamespace(id=75, pair="ETH/EUR", quote_currency="EUR",
                             provider_symbol="ETHEUR", tradingview_symbol="BINANCE:ETHEUR")

    class Catalog:
        def __init__(self, _session):
            pass

        async def get_asset(self, _symbol):
            return {"asset_class": "crypto"}

    class Markets:
        def __init__(self, _session):
            pass

        async def resolve(self, _base, _quote):
            return market

    class Repository:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, _market_id):
            return None

    class Ingestion:
        def __init__(self, _session):
            pass

        async def ingest_exact_market_snapshot(self, _market):
            return {"market_id": 75, "observed_at": None}

    monkeypatch.setattr(asset_catalog_api, "AssetCatalogService", Catalog)
    monkeypatch.setattr(asset_catalog_api, "TradingMarketService", Markets)
    monkeypatch.setattr(asset_catalog_api, "MarketDataRepository", Repository)
    monkeypatch.setattr(asset_catalog_api, "MarketDataIngestionService", Ingestion)
    result = asyncio.run(asset_catalog_api.select_crypto_trading_market(
        "ETH", "EUR", current_user={"id": 8}, session=session,
    ))
    assert result["pair"] == "ETH/EUR"
    assert result["snapshot_status"] == "pending"
