import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api import market_data_api


class FakeSession:
    def __init__(self, market):
        self.market = market

    async def get(self, _model, _id):
        return self.market


def test_exact_market_price_returns_only_the_market_id_and_quote(monkeypatch):
    market = SimpleNamespace(id=12, asset_symbol="BTC", quote_currency="EUR", is_active=True)
    snapshot = SimpleNamespace(price=71000, quote_currency="EUR", source_observed_at=datetime.now(timezone.utc))
    class FakeRepository:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, market_id):
            assert market_id == 12
            return snapshot

    monkeypatch.setattr(market_data_api, "MarketDataRepository", FakeRepository)
    result = asyncio.run(market_data_api.get_latest_exact_market_price(
        12, current_user={"id": 1}, db=FakeSession(market),
    ))
    assert (result["market_id"], result["quote_currency"], result["price"], result["stale"]) == (
        12, "EUR", 71000.0, False,
    )

    snapshot.quote_currency = "USDT"
    mismatched = asyncio.run(market_data_api.get_latest_exact_market_price(
        12, current_user={"id": 1}, db=FakeSession(market),
    ))
    assert mismatched["price"] is None
    assert mismatched["stale"] is True


def test_exact_market_price_rejects_unknown_or_inactive_market():
    with pytest.raises(HTTPException) as error:
        asyncio.run(market_data_api.get_latest_exact_market_price(
            999, current_user={"id": 1}, db=FakeSession(None),
        ))
    assert error.value.status_code == 404
