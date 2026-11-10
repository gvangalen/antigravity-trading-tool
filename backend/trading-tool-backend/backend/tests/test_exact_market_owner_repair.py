import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone


def test_owner_score_repair_uses_stored_pair_sources_only(monkeypatch):
    from backend.celery_task import market_task
    from backend.services import exact_market_indicator_service
    from backend.celery_task import store_daily_scores_task

    calls = []

    class Result:
        def mappings(self):
            return self

        def first(self):
            return {
                "id": 23, "asset_symbol": "BTC", "quote_currency": "USDT",
                "venue": "BINANCE", "provider": "binance",
                "provider_symbol": "BTCUSDT", "tradingview_symbol": "BINANCE:BTCUSDT",
                "source_verified_at": datetime.now(timezone.utc),
            }

    class Session:
        async def execute(self, statement, params):
            calls.append(("scope", str(statement), params))
            return Result()

        async def rollback(self):
            calls.append(("rollback",))

    @asynccontextmanager
    async def session_factory():
        yield Session()

    async def materialize(self, market, owner_ids, *, only_owner):
        calls.append(("materialize", market.id, owner_ids, only_owner))
        return {"written": 3}

    def score(user_id, market_id):
        calls.append(("score", user_id, market_id))
        return {"scores": {"market": 50, "macro": 20, "technical": 42}}

    monkeypatch.setattr(market_task, "async_session_factory", session_factory)
    monkeypatch.setattr(exact_market_indicator_service.ExactMarketIndicatorService,
                        "materialize", materialize)
    monkeypatch.setattr(store_daily_scores_task, "build_daily_scores_for_market", score)

    result = asyncio.run(market_task._repair_exact_market_owner_scores(7, 23))

    assert "w.user_id = :user_id" in calls[0][1]
    assert "w.market_id IS NULL AND a.quote_currency = tm.quote_currency" in calls[0][1]
    assert calls[0][2] == {"user_id": 7, "market_id": 23}
    assert calls[1:4] == [
        ("materialize", 23, {7}, True), ("rollback",), ("score", 7, 23),
    ]
    assert result == {"status": "complete", "market_id": 23, "user_id": 7,
                      "indicator_count": 3,
                      "scores": {"market": 50, "macro": 20, "technical": 42}}
