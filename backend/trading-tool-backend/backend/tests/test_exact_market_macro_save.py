import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.api import workspace_api
from backend.celery_task.celery_app import celery_app


def test_pair_macro_save_queues_history_without_waiting_for_provider(monkeypatch):
    steps = []
    market = SimpleNamespace(id=43, asset_symbol="BTC", quote_currency="USDT")
    session = SimpleNamespace(execute=AsyncMock(), commit=AsyncMock(), rollback=AsyncMock())
    service = SimpleNamespace(save=AsyncMock(side_effect=lambda *_args, **_kwargs: steps.append("save")))
    monkeypatch.setattr(workspace_api, "_pair_config", AsyncMock(
        return_value=(service, market, "macro", "gold_price")))
    monkeypatch.setattr(workspace_api, "queue_indicator_score_refresh",
                        lambda *_args, **_kwargs: steps.append("score"))
    monkeypatch.setattr(workspace_api, "queue_exact_market_refresh",
                        lambda *_args: steps.append("market"))
    monkeypatch.setattr(celery_app, "send_task",
                        lambda name, **kwargs: steps.append((name, kwargs)))

    payload = workspace_api.PairIndicatorWrite(
        market_id=43, category="macro", indicator="gold_price", mode="add",
        score_mode="standard", weight=1,
    )
    result = asyncio.run(workspace_api.put_pair_indicator_config(
        payload, current_user={"id": 7}, db=session))

    assert result["status"] == "pending_score"
    assert steps == [
        "save",
        ("backend.celery_task.indicator_history_task.bootstrap_indicator_histories",
         {"kwargs": {"user_id": 7, "symbol": "BTC", "category": "macro",
                     "indicator": "gold_price"}}),
        "score", "market",
    ]
    session.execute.assert_not_awaited()
