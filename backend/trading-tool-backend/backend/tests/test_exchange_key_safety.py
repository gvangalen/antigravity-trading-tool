import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import exchange_api
from backend.schemas.exchange_schema import ExchangeKeySchema
from backend.services.exchange_service import ExchangeService


class _Session:
    def __init__(self, pending=False):
        self.pending = pending
        self.queries = []

    async def execute(self, query, parameters):
        self.queries.append((str(query), parameters))
        return SimpleNamespace(first=lambda: (1,) if self.pending else None)


def test_connecting_second_exchange_requires_disconnecting_first(monkeypatch):
    saved = []

    class Repository:
        def __init__(self, _db):
            pass

        async def get_active_keys(self, _user_id):
            return [SimpleNamespace(exchange_name="bitvavo")]

        async def save_exchange_key(self, *_args):
            saved.append(True)

    monkeypatch.setattr(exchange_api, "ExchangeRepository", Repository)
    payload = ExchangeKeySchema(exchange_name="bybit", api_key="test", api_secret="test")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_api.save_exchange_keys(payload, {"id": 1}, _Session()))
    assert exc.value.status_code == 409
    assert saved == []


def test_pending_live_order_prevents_exchange_disconnection(monkeypatch):
    deleted = []

    class Repository:
        def __init__(self, _db):
            pass

        async def delete_exchange_key(self, *_args):
            deleted.append(True)

    monkeypatch.setattr(exchange_api, "ExchangeRepository", Repository)
    session = _Session(pending=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(exchange_api.delete_exchange_keys("bitvavo", {"id": 1}, session))
    assert exc.value.status_code == 409
    assert deleted == []
    pending_sql = next(sql for sql, _ in session.queries if "FROM bot_orders" in sql)
    assert "exchange_name IS NULL" in pending_sql


def test_exchange_valuation_requires_current_two_sided_quote():
    assert ExchangeService.verified_eur_ticker_price(
        {"symbol": "USDT/EUR", "last": 0.9, "bid": 0.899, "ask": 0.901}, "USDT"
    ) == 0.9
    with pytest.raises(ValueError, match="stale"):
        ExchangeService.verified_eur_ticker_price(
            {"symbol": "USDT/EUR", "last": 0.9, "bid": 0.899, "ask": 0.901, "timestamp": 1}, "USDT"
        )
    with pytest.raises(ValueError, match="wide"):
        ExchangeService.verified_eur_ticker_price(
            {"symbol": "USDT/EUR", "last": 0.9, "bid": 0.8, "ask": 1.0}, "USDT"
        )
    with pytest.raises(ValueError, match="spot EUR pair"):
        ExchangeService.verified_eur_ticker_price(
            {"symbol": "USDT/EUR:EUR", "last": 0.9, "bid": 0.899, "ask": 0.901}, "USDT"
        )
