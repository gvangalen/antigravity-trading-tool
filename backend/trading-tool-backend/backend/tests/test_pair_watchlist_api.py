import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import watchlist_api


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
