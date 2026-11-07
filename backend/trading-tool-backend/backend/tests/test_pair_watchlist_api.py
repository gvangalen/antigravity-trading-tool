import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.api import watchlist_api
from backend.services.workspace_data_service import WorkspaceDataService, _keep_watchlist_row


class _Scalars:
    def __init__(self, rows):
        self.rows = rows

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class _Result:
    def __init__(self, rows=(), rowcount=0):
        self.rows = rows
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows

    def scalars(self):
        return _Scalars(self.rows)


class _Session:
    def __init__(self, results):
        self.results = iter(results)
        self.statements = []
        self.added = []
        self.commits = 0

    async def execute(self, statement):
        self.statements.append(str(statement))
        return next(self.results)

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        self.commits += 1


def test_two_pairs_can_be_added_and_one_removed_independently(monkeypatch):
    eur = SimpleNamespace(id=11, quote_currency="EUR")
    usdt = SimpleNamespace(id=12, quote_currency="USDT")
    session = _Session([
        _Result([eur]), _Result(), _Result(),
        _Result([usdt]), _Result(), _Result(),
        _Result(rowcount=1),
    ])
    refreshed = []
    monkeypatch.setattr(watchlist_api, "queue_exact_market_refresh", refreshed.append)
    user = {"id": 9}

    asyncio.run(watchlist_api.add_to_watchlist(
        watchlist_api.WatchlistAddRequest(symbol="BTC", market_id=11), user, session))
    asyncio.run(watchlist_api.add_to_watchlist(
        watchlist_api.WatchlistAddRequest(symbol="BTC", market_id=12), user, session))

    assert [(row.symbol, row.market_id) for row in session.added] == [("BTC", 11), ("BTC", 12)]
    assert refreshed == [11, 12]
    assert session.commits == 2

    asyncio.run(watchlist_api.remove_from_watchlist("BTC", 11, user, session))
    assert "watchlists.market_id = :market_id_1" in session.statements[-1]
    assert session.commits == 3


def test_symbol_only_delete_requires_pair_choice_when_ambiguous():
    session = _Session([_Result([101, 102])])
    with pytest.raises(HTTPException) as error:
        asyncio.run(watchlist_api.remove_from_watchlist("BTC", None, {"id": 9}, session))
    assert error.value.status_code == 409
    assert session.commits == 0


def test_adding_eur_preserves_legacy_usdt_watchlist_row(monkeypatch):
    eur = SimpleNamespace(id=11, quote_currency="EUR")
    legacy = SimpleNamespace(symbol="ETH", market_id=None)
    session = _Session([_Result([eur]), _Result(), _Result([legacy])])
    catalog = SimpleNamespace(get_asset=AsyncMock(return_value={"quote_currency": "USDT"}))
    monkeypatch.setattr(watchlist_api, "AssetCatalogService", lambda _session: catalog)
    monkeypatch.setattr(watchlist_api, "queue_exact_market_refresh", lambda _market_id: None)

    asyncio.run(watchlist_api.add_to_watchlist(
        watchlist_api.WatchlistAddRequest(symbol="ETH", market_id=11), {"id": 9}, session))

    assert legacy.market_id is None
    assert [(row.symbol, row.market_id) for row in session.added] == [("ETH", 11)]
    assert session.commits == 1


def test_selecting_default_quote_migrates_legacy_row(monkeypatch):
    usdt = SimpleNamespace(id=12, quote_currency="USDT")
    legacy = SimpleNamespace(symbol="ETH", market_id=None)
    session = _Session([_Result([usdt]), _Result(), _Result([legacy])])
    catalog = SimpleNamespace(get_asset=AsyncMock(return_value={"quote_currency": "USDT"}))
    monkeypatch.setattr(watchlist_api, "AssetCatalogService", lambda _session: catalog)
    monkeypatch.setattr(watchlist_api, "queue_exact_market_refresh", lambda _market_id: None)

    asyncio.run(watchlist_api.add_to_watchlist(
        watchlist_api.WatchlistAddRequest(symbol="ETH", market_id=12), {"id": 9}, session))

    assert legacy.market_id == 12
    assert session.added == []
    assert session.commits == 1


def test_workspace_keeps_legacy_usdt_row_beside_eur_pair():
    base = {"symbol": "ETH", "quote_currency": "USDT"}
    eur = {"symbol": "ETH", "market_id": 11, "quote_currency": "EUR"}
    assert _keep_watchlist_row(base, {"ETH"}, {("ETH", "EUR")}, {"ETH"})
    assert _keep_watchlist_row(eur, {"ETH"}, {("ETH", "EUR")}, {"ETH"})
    assert not _keep_watchlist_row(base, {"ETH"}, {("ETH", "USDT")}, {"ETH"})
    assert not _keep_watchlist_row(base, {"ETH"}, {("ETH", "EUR")}, set())


def test_workspace_returns_legacy_usdt_and_exact_eur_rows(monkeypatch):
    legacy = SimpleNamespace(symbol="ETH", market_id=None)
    exact = SimpleNamespace(symbol="ETH", market_id=11)
    eur = SimpleNamespace(id=11, quote_currency="EUR", tradingview_symbol="BINANCE:ETHEUR")
    session = _Session([_Result([(legacy, None), (exact, eur)])])
    service = object.__new__(WorkspaceDataService)
    service.session = session
    service.scores = SimpleNamespace(fetch_daily_scores_batch=AsyncMock(return_value={}))
    match = SimpleNamespace(for_asset=AsyncMock(return_value={
        "benchmark_score": None, "source_status": "insufficient_data", "as_of": None,
    }))
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService",
                        lambda *_args, **_kwargs: match)
    repository = SimpleNamespace(get_latest_exact_market_snapshot=AsyncMock(return_value=None))
    monkeypatch.setattr("backend.infrastructure.repositories.market_data_repository.MarketDataRepository",
                        lambda _session: repository)

    result = asyncio.run(service._build_watchlist_payload(
        9, ["ETH"],
        asset_catalog={"ETH": {"display_name": "Ethereum", "asset_class": "crypto", "quote_currency": "USDT"}},
        quote_map={"ETH": {"price": 2200, "quote_currency": "USDT", "timestamp": None}},
    ))

    assert [(row["symbol"], row.get("market_id"), row["quote_currency"]) for row in result["rows"]] == [
        ("ETH", None, "USDT"), ("ETH", 11, "EUR"),
    ]
