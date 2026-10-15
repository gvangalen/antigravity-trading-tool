import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.services import live_portfolio_allocation_service as service


def test_broker_balance_is_counted_once_and_unpriced_asset_keeps_cash(monkeypatch):
    service._account_cache.clear()
    class Repo:
        def __init__(self, _session):
            pass

        async def get_active_keys(self, user_id):
            assert user_id == 7
            return [SimpleNamespace(id=1, exchange_name="bitvavo", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    class Client:
        has = {"fetchTickers": True}

        async def fetch_balance(self):
            return {"timestamp": datetime.now(timezone.utc).timestamp() * 1000,
                    "total": {"EUR": 300, "BTC": 1, "ETH": 2}, "free": {"EUR": 250}}

        async def fetch_tickers(self, pairs):
            assert pairs == ["BTC/EUR", "ETH/EUR"]
            return {"BTC/EUR": {"symbol": "BTC/EUR", "last": 1000, "bid": 999, "ask": 1001,
                                "timestamp": datetime.now(timezone.utc).timestamp() * 1000}}

        async def fetch_ticker(self, pair):
            raise RuntimeError(f"No price for {pair}")

        async def close(self):
            pass

    async def client(*_args):
        return Client()

    monkeypatch.setattr(service, "ExchangeRepository", Repo)
    monkeypatch.setattr(service.ExchangeService, "get_client", client)
    account = asyncio.run(service.read_live_account(None, 7))
    assert account["total_eur"] == 300
    assert account["cash_eur"] == 250
    assert account["positions"] == {"BTC": 1, "ETH": 2}
    assert account["prices_eur"] == {"BTC": 1000}
    assert account["position_value_eur"] is None


def test_broker_balance_without_provider_time_discloses_retrieval_basis(monkeypatch):
    service._account_cache.clear()

    class Repo:
        def __init__(self, _session): pass
        async def get_active_keys(self, _user_id):
            return [SimpleNamespace(id=2, exchange_name="bitvavo", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    class Client:
        async def fetch_balance(self):
            return {"total": {"EUR": 100}, "free": {"EUR": 100}}
        async def close(self): pass

    async def client(*_args): return Client()
    monkeypatch.setattr(service, "ExchangeRepository", Repo)
    monkeypatch.setattr(service.ExchangeService, "get_client", client)
    account = asyncio.run(service.read_live_account(None, 8))
    assert account["cash_eur"] == 100
    assert account["balance_time_basis"] == "retrieval"


@pytest.mark.parametrize("balance", [
    {"total": {"EUR": None}, "free": {"EUR": 0}},
    {"total": {"EUR": 0}, "free": {"EUR": None}},
    {"total": {"EUR": 0, "BTC": None}, "free": {"EUR": 0}},
    {"total": {}, "free": {}},
    {"total": {"BTC": 1}, "free": {"BTC": 1}},
])
def test_incomplete_broker_balance_never_becomes_zero_value_account(monkeypatch, balance):
    service._account_cache.clear()

    class Repo:
        def __init__(self, _session): pass
        async def get_active_keys(self, _user_id):
            return [SimpleNamespace(id=22, exchange_name="bitvavo", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    class Client:
        async def fetch_balance(self): return balance
        async def close(self): pass

    async def client(*_args): return Client()
    monkeypatch.setattr(service, "ExchangeRepository", Repo)
    monkeypatch.setattr(service.ExchangeService, "get_client", client)
    assert asyncio.run(service.read_live_account(None, 22)) is None


def test_twenty_asset_live_account_uses_one_client_and_one_batch(monkeypatch):
    service._account_cache.clear()
    calls = {"clients": 0, "batches": 0}

    class Repo:
        def __init__(self, _session): pass
        async def get_active_keys(self, _user_id):
            return [SimpleNamespace(id=3, exchange_name="bitvavo", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    class Client:
        has = {"fetchTickers": True}
        async def fetch_balance(self):
            return {"timestamp": datetime.now(timezone.utc).timestamp() * 1000,
                    "total": {"EUR": 100, **{f"ASSET{i}": 1 for i in range(20)}},
                    "free": {"EUR": 100}}
        async def fetch_tickers(self, pairs):
            calls["batches"] += 1
            return {pair: {"symbol": pair, "last": 10, "bid": 9.99, "ask": 10.01,
                           "timestamp": datetime.now(timezone.utc).timestamp() * 1000} for pair in pairs}
        async def close(self): pass

    async def client(*_args):
        calls["clients"] += 1
        return Client()
    monkeypatch.setattr(service, "ExchangeRepository", Repo)
    monkeypatch.setattr(service.ExchangeService, "get_client", client)
    account = asyncio.run(service.read_live_account(None, 9))
    assert account["position_value_eur"] == 200
    assert calls == {"clients": 1, "batches": 1}


def test_ticker_timeout_keeps_verified_cash_without_inventing_position_value(monkeypatch):
    service._account_cache.clear()

    class Repo:
        def __init__(self, _session): pass
        async def get_active_keys(self, _user_id):
            return [SimpleNamespace(id=23, exchange_name="bitvavo", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    class Client:
        has = {"fetchTickers": True}
        async def fetch_balance(self):
            return {"total": {"EUR": 100, "BTC": 1}, "free": {"EUR": 80}}
        async def fetch_tickers(self, _pairs):
            raise asyncio.TimeoutError()
        async def fetch_ticker(self, _pair):
            raise asyncio.TimeoutError()
        async def close(self): pass

    async def client(*_args): return Client()
    monkeypatch.setattr(service, "ExchangeRepository", Repo)
    monkeypatch.setattr(service.ExchangeService, "get_client", client)
    account = asyncio.run(service.read_live_account(None, 23))
    assert account["cash_eur"] == 80
    assert account["position_value_eur"] is None
    assert account["positions"] == {"BTC": 1}


class Session:
    def __init__(self, owned):
        self.owned = owned
        self.calls = []
        self.committed = False

    async def execute(self, statement, params):
        sql = str(statement)
        self.calls.append((sql, params))
        if "SELECT id FROM bot_configs" in sql:
            return [SimpleNamespace(id=bot_id) for bot_id in self.owned]
        return []

    async def commit(self):
        self.committed = True


def test_allocation_rejects_overdraw_and_foreign_bot_before_writing():
    account = {"exchange_name": "bitvavo", "cash_eur": 100}
    session = Session({1})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.replace_allocations(session, 7, account, [
            {"bot_id": 1, "amount_eur": "101"}]))
    assert exc.value.status_code == 409
    assert not session.calls

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.replace_allocations(session, 7, account, [
            {"bot_id": 2, "amount_eur": "50"}]))
    assert exc.value.status_code == 404
    assert not any("DELETE FROM" in sql for sql, _ in session.calls)
    assert not session.committed


def test_allocation_replaces_owner_rows_only_and_never_writes_orders():
    account = {"exchange_name": "bitvavo", "cash_eur": 100}
    session = Session({1, 2})
    saved = asyncio.run(service.replace_allocations(session, 7, account, [
        {"bot_id": 1, "amount_eur": "20.00"},
        {"bot_id": 2, "amount_eur": "30.00"},
    ]))
    assert saved == {1: 20, 2: 30}
    assert session.committed
    assert all(params.get("user_id") == 7 for _, params in session.calls)
    assert sum("INSERT INTO live_portfolio_cash_allocations" in sql for sql, _ in session.calls) == 2
    assert not any("bot_orders" in sql or "bot_ledger" in sql for sql, _ in session.calls)
