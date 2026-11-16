import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone


def test_pair_quote_move_still_dispatches_plan_review_when_score_fails(monkeypatch):
    from backend.celery_task import market_task, store_daily_scores_task
    from backend.services import (exact_market_indicator_service,
                                  market_data_ingestion_service,
                                  pair_indicator_config_service)

    events = []

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [{
                "id": 23, "asset_symbol": "BTC", "quote_currency": "USDT",
                "venue": "BINANCE", "provider": "binance",
                "provider_symbol": "BTCUSDT", "tradingview_symbol": "BINANCE:BTCUSDT",
                "source_verified_at": datetime.now(timezone.utc),
            }]

    class Session:
        async def execute(self, *_args, **_kwargs):
            return Result()

        async def rollback(self):
            events.append("rollback")

        async def commit(self):
            events.append("quote_committed")

    @asynccontextmanager
    async def session_factory():
        yield Session()

    async def ingest(self, _market):
        await self.session.commit()
        return {"observed_at": datetime.now(timezone.utc).isoformat()}

    async def bootstrap(self, _market, *, required_days):
        return {"status": "ready", "observed_days": required_days}

    async def materialize(self, _market):
        return {"owners": [7], "written": 2}

    async def configs(self, _user_id, _market):
        return []

    def score(_user_id, _market_id):
        events.append("score_failed")
        raise RuntimeError("score unavailable")

    def dispatch(*args):
        events.append(("plan_review", args))

    monkeypatch.setattr(market_task, "async_session_factory", session_factory)
    monkeypatch.setattr(market_data_ingestion_service.MarketDataIngestionService,
                        "ingest_exact_market_snapshot", ingest)
    monkeypatch.setattr("backend.services.indicator_history_bootstrap.IndicatorHistoryBootstrap.bootstrap_exact_market",
                        bootstrap)
    monkeypatch.setattr(exact_market_indicator_service.ExactMarketIndicatorService,
                        "materialize", materialize)
    monkeypatch.setattr(pair_indicator_config_service.PairIndicatorConfigService,
                        "rows", configs)
    monkeypatch.setattr(store_daily_scores_task, "build_daily_scores_for_market", score)
    monkeypatch.setattr(store_daily_scores_task.reconcile_coach_feed_score, "delay", dispatch)

    result = asyncio.run(market_task._sync_exact_market_snapshots(market_id=23))

    assert result["scopes"][0]["status"] == "ready"
    assert result["scopes"][0]["score_count"] == 0
    assert events == ["rollback", "quote_committed", "score_failed",
                      ("plan_review", (7, "BTC", 23))]


def test_setup_change_dispatches_exact_pair_scope(monkeypatch):
    from backend.celery_task import store_daily_scores_task
    from backend.services.setup_service import SetupService

    calls = []
    monkeypatch.setattr(store_daily_scores_task.reconcile_coach_feed_score, "delay",
                        lambda *args: calls.append(args))

    SetupService._notify_coach_feed(7, "BTC", 23)
    SetupService._notify_coach_feed(7, "AAPL")

    assert calls == [(7, "BTC", 23), (7, "AAPL")]


def test_deleted_pair_setup_resolves_its_active_plan_card(monkeypatch):
    from backend.infrastructure.repositories.setup_repository import SetupRepository
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    class Session:
        async def execute(self, statement, params):
            assert params == {"user_id": 7, "symbol": "BTC", "market_id": "23"}
            self.event_type = ("plan_review" if "event_type='plan_review'" in str(statement)
                               else "improvement_suggestion")
            return self

        def mappings(self):
            return self

        def all(self):
            return ([{"event_key": "plan-review:81"}] if self.event_type == "plan_review"
                    else [])

    async def setups(self, user_id):
        assert user_id == 7
        return []

    resolved = []

    async def resolve(self, **kwargs):
        resolved.append(kwargs)

    monkeypatch.setattr(SetupRepository, "get_all_setups", setups)
    monkeypatch.setattr(FinnCoachFeedService, "resolve", resolve)

    result = asyncio.run(FinnCoachFeedService(Session()).reconcile_plan_reviews(
        user_id=7, symbol="BTC", market_id=23))

    assert result == []
    assert resolved == [{"user_id": 7, "event_key": "plan-review:81"}]
