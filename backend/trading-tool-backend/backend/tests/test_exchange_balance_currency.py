import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.api import exchange_api


def test_shared_exchange_balance_never_labels_usdt_as_eur(monkeypatch):
    seen = []

    class Repository:
        def __init__(self, _db):
            pass

        async def get_active_keys(self, user_id):
            seen.append(user_id)
            return [SimpleNamespace(exchange_name="test", api_key="encrypted", api_secret="encrypted", api_passphrase=None)]

    monkeypatch.setattr(exchange_api, "ExchangeRepository", Repository)
    monkeypatch.setattr(exchange_api.ExchangeService, "get_client", AsyncMock(return_value=object()))
    fetch = AsyncMock(return_value={"total": {"EUR": 100, "USDT": 25}, "free": {}, "used": {}})
    monkeypatch.setattr(exchange_api.ExchangeService, "fetch_balance", fetch)

    mixed = asyncio.run(exchange_api.get_exchange_balances(current_user={"id": 17}, db=object()))
    assert seen == [17]
    assert mixed[0]["total_eur"] is None
    assert mixed[0]["total"]["USDT"] == 25

    fetch.return_value = {"total": {"EUR": 100}, "free": {}, "used": {}}
    eur_only = asyncio.run(exchange_api.get_exchange_balances(current_user={"id": 17}, db=object()))
    assert eur_only[0]["total_eur"] == 100
