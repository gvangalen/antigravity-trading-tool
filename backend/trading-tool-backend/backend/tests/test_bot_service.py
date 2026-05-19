import pytest
from fastapi import HTTPException

from backend.services.bot_service import BotService


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeSession:
    def __init__(self, *, duplicate_strategy_bot_id=None):
        self.duplicate_strategy_bot_id = duplicate_strategy_bot_id

    async def execute(self, query, params=None):
        sql = str(query).lower()
        params = params or {}
        if "lower(name)" in sql:
            return _FakeResult(None)
        if "from strategies s" in sql:
            return _FakeResult((params.get("strategy_id"), "BTC"))
        if "from bot_configs" in sql and "strategy_id" in sql:
            row = (self.duplicate_strategy_bot_id,) if self.duplicate_strategy_bot_id else None
            return _FakeResult(row)
        return _FakeResult(None)


def test_bot_payload_validation_normalizes_transactional_fields():
    service = BotService(_FakeSession())
    payload = {
        "name": "  BTC Paper Bot  ",
        "strategy_id": 42,
        "mode": "Semi",
        "is_live": False,
        "risk_profile": "BALANCED",
        "cadence": "DAILY",
        "base_currency": "eur",
        "budget_total_eur": 1000,
        "budget_daily_limit_eur": 100,
        "budget_min_order_eur": 10,
        "budget_max_order_eur": 50,
    }

    import asyncio
    asyncio.run(service.validate_bot_payload(payload, user_id=1))

    assert payload["name"] == "BTC Paper Bot"
    assert payload["symbol"] == "BTC"
    assert payload["mode"] == "semi-auto"
    assert payload["risk_profile"] == "balanced"
    assert payload["cadence"] == "daily"
    assert payload["base_currency"] == "EUR"


def test_bot_creation_rejects_duplicate_strategy_bot():
    service = BotService(_FakeSession(duplicate_strategy_bot_id=7))
    payload = {
        "name": "BTC Bot",
        "strategy_id": 42,
        "mode": "manual",
        "is_live": False,
        "risk_profile": "balanced",
        "cadence": "daily",
        "base_currency": "EUR",
    }

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.validate_bot_payload(payload, user_id=1))

    assert exc.value.status_code == 409
    assert "bestaat al bot #7" in exc.value.detail


def test_bot_update_allows_current_bot_strategy_link():
    service = BotService(_FakeSession(duplicate_strategy_bot_id=7))
    payload = {
        "name": "BTC Bot",
        "strategy_id": 42,
        "mode": "manual",
        "is_live": False,
        "risk_profile": "balanced",
        "cadence": "daily",
        "base_currency": "EUR",
    }

    import asyncio
    asyncio.run(service.validate_bot_payload(payload, user_id=1, is_update=True, bot_id=7))

    assert payload["symbol"] == "BTC"
