import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from backend.api import workspace_api
from backend.celery_task.celery_app import celery_app
from backend.services.indicator_history_bootstrap import IndicatorHistoryBootstrap
from backend.services.macro_data_service import MacroDataService


def test_pair_macro_save_backfills_history_before_scoring(monkeypatch):
    steps = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    market = SimpleNamespace(id=43, asset_symbol="BTC", quote_currency="USDT")

    class Result:
        def first(self):
            return (4200.0, 65, now)

    session = SimpleNamespace(execute=AsyncMock(return_value=Result()),
                              commit=AsyncMock(), rollback=AsyncMock())
    service = SimpleNamespace(save=AsyncMock(side_effect=lambda *_args, **_kwargs: steps.append("save")))
    monkeypatch.setattr(workspace_api, "_pair_config", AsyncMock(
        return_value=(service, market, "macro", "gold_price")))

    async def bootstrap(*_args):
        steps.append("history")
        return {"status": "ready", "inserted": 6}

    async def materialize(*_args, **_kwargs):
        steps.append("measurement")

    monkeypatch.setattr(IndicatorHistoryBootstrap, "bootstrap_macro", bootstrap)
    monkeypatch.setattr(MacroDataService, "add_macro_indicator", materialize)
    monkeypatch.setattr(workspace_api, "queue_indicator_score_refresh", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(workspace_api, "queue_exact_market_refresh", lambda *_args: True)
    monkeypatch.setattr(celery_app, "send_task", lambda *_args, **_kwargs: None)

    payload = workspace_api.PairIndicatorWrite(
        market_id=43, category="macro", indicator="gold_price", mode="add",
        score_mode="standard", weight=1,
    )
    result = asyncio.run(workspace_api.put_pair_indicator_config(
        payload, current_user={"id": 7}, db=session))

    assert result["status"] == "ready"
    assert steps == ["save", "history", "measurement"]
