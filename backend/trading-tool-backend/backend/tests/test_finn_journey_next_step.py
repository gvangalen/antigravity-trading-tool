import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.setup_service import SetupService


class Rows:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row


def test_verified_setup_followup_uses_owner_and_saved_links():
    row = {"id": 42, "name": "Mijn BTC", "symbol": "BTC", "quote_currency": "USDT",
           "strategy_id": None, "has_bot": False}

    async def execute(sql, params):
        assert params == {"user_id": 7, "setup_id": 42,
                          "expected_strategy_id": expected[0]}
        assert "st.id=CAST(:expected_strategy_id AS INTEGER)" in str(sql)
        assert "b.strategy_id=CAST(:expected_strategy_id AS INTEGER)" in str(sql)
        return Rows(row)

    service = FinnV2ExecutionService.__new__(FinnV2ExecutionService)
    service.session = SimpleNamespace(execute=execute)
    expected = [None]
    result = {"setup_id": 42}
    assert asyncio.run(service._journey_next_step(7, "create_setup", result)) == {
        "step": "strategy", "setup_id": 42, "setup_name": "Mijn BTC", "pair": "BTC/USDT",
    }
    row["strategy_id"] = 91
    expected[0] = 91
    strategy_result = {"setup_id": 42, "strategy_id": 91}
    assert asyncio.run(service._journey_next_step(7, "create_strategy", strategy_result)) == {
        "step": "paper", "setup_id": 42, "strategy_id": 91,
        "setup_name": "Mijn BTC", "pair": "BTC/USDT",
    }
    row["has_bot"] = True
    assert asyncio.run(service._journey_next_step(7, "create_strategy", strategy_result)) is None


def test_strategy_followup_never_uses_a_concurrent_different_strategy():
    async def execute(sql, params):
        assert params["expected_strategy_id"] == 91
        assert "st.id=CAST(:expected_strategy_id AS INTEGER)" in str(sql)
        return Rows({"id": 42, "name": "BTC", "symbol": "BTC",
                     "quote_currency": "USDT", "strategy_id": None,
                     "has_bot": False})

    service = FinnV2ExecutionService.__new__(FinnV2ExecutionService)
    service.session = SimpleNamespace(execute=execute)
    assert asyncio.run(service._journey_next_step(
        7, "create_strategy", {"setup_id": 42, "strategy_id": 91},
    )) is None


def test_journey_followup_never_uses_unverified_or_foreign_setup():
    service = FinnV2ExecutionService.__new__(FinnV2ExecutionService)
    service.session = SimpleNamespace(execute=AsyncMock(return_value=Rows(None)))
    assert asyncio.run(service._journey_next_step(7, "create_setup", {"setup_id": 42})) is None
    assert asyncio.run(service._journey_next_step(7, "create_setup", {"setup_id": "42"})) is None
    assert asyncio.run(service._journey_next_step(7, "update_setup", {"setup_id": 42})) is None


def test_setup_write_dispatches_journey_independently_of_score(monkeypatch):
    from backend.celery_task import store_daily_scores_task as module

    journey = Mock()
    score = SimpleNamespace(delay=Mock(side_effect=RuntimeError("score unavailable")))
    from backend.celery_task.celery_app import celery_app
    monkeypatch.setattr(celery_app, "send_task", journey)
    monkeypatch.setattr(module, "reconcile_coach_feed_score", score)
    SetupService._notify_coach_feed(7, "BTC", 34)
    journey.assert_called_once_with(
        "backend.celery_task.store_daily_scores_task.reconcile_coach_feed_journey",
        args=[7, "BTC", 34],
    )
