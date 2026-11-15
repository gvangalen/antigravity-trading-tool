"""The active coach reads exact owned market evidence and never authorizes a trade."""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import finn_coach_feed_service as feed
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService


@pytest.mark.parametrize(
    "asset, market_id, pair, status, source_status, expected_advice",
    [
        ("BTC", 11, "BTC/EUR", "outside_conditions", "available", "Wacht met een nieuwe instap"),
        ("BTC", 12, "BTC/USDT", "matches", "available", "geen instapsignaal"),
        ("ETH", 21, "ETH/EUR", "insufficient_data", "stale_sources", "actuele score is niet verifieerbaar"),
        ("AAPL", None, None, "outside_conditions", "available", "Wacht met een nieuwe instap"),
    ],
)
def test_move_creates_owner_scoped_plan_review_for_each_market(
    monkeypatch, asset, market_id, pair, status, source_status, expected_advice,
):
    monkeypatch.delenv("FINN_COACH_MOVE_THRESHOLD_PCT", raising=False)
    monkeypatch.delenv("FINN_COACH_QUOTE_MAX_AGE_MINUTES", raising=False)
    setups = [{"id": 7, "name": "Eigen plan", "symbol": asset,
               "market_id": market_id, "quote_currency": pair.split("/")[1] if pair else None},
              {"id": 8, "name": "Ander paar", "symbol": asset,
               "market_id": 99 if market_id != 99 else 98, "quote_currency": "USD"}]
    matcher_calls = []
    quote_calls = []

    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, owner):
            assert owner == 42
            return setups

    class Matcher:
        def __init__(self, _session):
            pass

        async def for_asset(self, owner, symbol, *, setups, market_id):
            matcher_calls.append((owner, symbol, [setup["id"] for setup in setups], market_id))
            return {"source_status": source_status, "benchmark_score": 68 if status == "matches" else 35,
                    "as_of": "2026-11-15", "component_source_status": {"market_score": "fresh"},
                    "component_source_observed_at": {"market": {"change_24h": "2026-11-15T10:00:00Z"}},
                    "matches": [{"setup_id": 7, "status": status, "trading_pair": pair,
                                 "conditions": {"benchmark": {"minimum": 61, "maximum": 75}}}]}

    class Market:
        def __init__(self, _session):
            pass

        async def get_latest_exact_market_snapshot(self, selected):
            quote_calls.append(("exact", selected))
            return SimpleNamespace(change_24h=-12.4, source_observed_at=datetime.now(timezone.utc))

        async def get_latest_quoted_snapshot(self, selected):
            quote_calls.append(("asset", selected))
            return SimpleNamespace(change_24h=-12.4, source_observed_at=datetime.now(timezone.utc))

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", Matcher)
    monkeypatch.setattr("backend.infrastructure.repositories.market_data_repository.MarketDataRepository", Market)
    monkeypatch.setattr("backend.utils.scoring_utils.score_source_is_fresh", lambda *_args, **_kwargs: True)
    class EmptyActiveFeed:
        async def execute(self, *_args, **_kwargs):
            return self

        def mappings(self):
            return self

        def all(self):
            return []

    coach = feed.FinnCoachFeedService(EmptyActiveFeed())
    coach.publish = AsyncMock(return_value="new-item")
    coach.resolve = AsyncMock()

    assert asyncio.run(coach.reconcile_plan_reviews(
        user_id=42, symbol=asset.lower(), market_id=market_id)) == ["new-item"]
    assert matcher_calls == [(42, asset, [7], market_id)]
    assert quote_calls == [(("exact", market_id) if market_id else ("asset", asset))]
    event = coach.publish.await_args.kwargs
    assert event["event_key"] == "plan-review:7"
    assert event["subject_type"] == "setup"
    assert event["evidence"]["trading_pair"] == pair
    assert event["evidence"]["plan_status"] == status
    assert event["evidence"]["source_status"] == source_status
    assert expected_advice in feed._fallback("plan_review", "Eigen plan", event["evidence"])["nl"]["body"]
    body = feed._fallback("plan_review", "Eigen plan", event["evidence"])["nl"]["body"]
    assert "-12,4%" in body
    assert ("Gemeten score" in body) is (source_status == "available")
    if source_status == "available":
        assert "61–75" in body
    assert "trade" not in event
    coach.resolve.assert_not_awaited()


def test_old_quote_resolves_plan_review_without_new_advice(monkeypatch):
    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, owner):
            return [{"id": 7, "name": "Apple plan", "symbol": "AAPL", "market_id": None}]

    class Matcher:
        def __init__(self, _session):
            pass

        async def for_asset(self, *_args, **_kwargs):
            return {"source_status": "available", "matches": [{"setup_id": 7, "status": "matches"}]}

    class Market:
        def __init__(self, _session):
            pass

        async def get_latest_quoted_snapshot(self, _asset):
            return SimpleNamespace(change_24h=-15, source_observed_at=datetime(2020, 1, 1, tzinfo=timezone.utc))

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", Matcher)
    monkeypatch.setattr("backend.infrastructure.repositories.market_data_repository.MarketDataRepository", Market)
    monkeypatch.setattr("backend.utils.scoring_utils.score_source_is_fresh", lambda *_args, **_kwargs: False)
    class EmptyActiveFeed:
        async def execute(self, *_args, **_kwargs):
            return self

        def mappings(self):
            return self

        def all(self):
            return []

    coach = feed.FinnCoachFeedService(EmptyActiveFeed())
    coach.publish = AsyncMock()
    coach.resolve = AsyncMock()

    assert asyncio.run(coach.reconcile_plan_reviews(user_id=42, symbol="AAPL")) == []
    coach.publish.assert_not_awaited()
    coach.resolve.assert_awaited_once_with(user_id=42, event_key="plan-review:7")


def test_discussing_plan_review_rechecks_exact_pair_before_answer(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000007"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 42
        return {"id": item_id, "event_type": "plan_review", "subject_type": "setup",
                "subject_id": "7", "symbol": "BTC", "status": "read",
                "source_observed_at": "2026-11-15T10:00:00Z",
                "evidence": {"market_id": 11, "trading_pair": "BTC/EUR",
                             "plan_status": "outside_conditions", "benchmark_score": 35,
                             "change_24h": -12.4, "source_status": "available"}}

    class Matcher:
        def __init__(self, _session):
            pass

        async def for_asset(self, owner, symbol, *, setups, market_id):
            assert (owner, symbol, market_id) == (42, "BTC", 11)
            assert [setup["id"] for setup in setups] == [7]
            return {"source_status": "stale_sources", "matches": [
                {"setup_id": 7, "name": "Eigen plan", "status": "insufficient_data"}]}

    monkeypatch.setattr(feed.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", Matcher)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.setup_repository.SetupRepository.get_setup_by_id",
        AsyncMock(return_value={"id": 7, "symbol": "BTC", "market_id": 11}),
    )
    historical, current = asyncio.run(FinnV2ReasoningContextService(object())._current_feed_evidence(
        SimpleNamespace(user_id=42, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_event_facts"]["trading_pair"] == "BTC/EUR"
    assert historical.facts["historical_event_facts"]["benchmark_score"] == 35
    assert current.facts["current_source_status"] == "stale_sources"
    assert current.facts["current_setup"]["status"] == "insufficient_data"
    assert current.facts["current_trade_signal_confirmed"] is False


def test_pair_score_worker_routes_only_the_exact_plan_review(monkeypatch):
    from backend.celery_task import store_daily_scores_task as tasks

    calls = []

    class Context:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def commit(self):
            calls.append("commit")

    class Coach:
        def __init__(self, _session):
            pass

        async def reconcile_score_asset(self, **_kwargs):
            raise AssertionError("legacy asset score was read for an exact pair")

        async def reconcile_plan_reviews(self, **kwargs):
            calls.append(kwargs)
            return ["item-1"]

    monkeypatch.setattr("backend.infrastructure.database.async_session_factory", Context)
    monkeypatch.setattr(feed, "FinnCoachFeedService", Coach)
    monkeypatch.setattr("backend.celery_task.finn_v2_task._run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(tasks.generate_coach_feed_copy, "delay", lambda *args: calls.append(args))

    tasks.reconcile_coach_feed_score.run(42, "BTC", 11)
    assert calls == [{"user_id": 42, "symbol": "BTC", "market_id": 11},
                     "commit", (42, "item-1")]


def test_completed_pair_score_dispatches_coach_after_commit(monkeypatch):
    from backend.celery_task import store_daily_scores_task as tasks

    events = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, query, _params):
            if "INSERT INTO daily_scores" in query:
                events.append("score_written")

        def fetchone(self):
            return ("BTC",)

    class Connection:
        def cursor(self):
            return Cursor()

        def commit(self):
            events.append("commit")

        def close(self):
            events.append("close")

        def rollback(self):
            raise AssertionError("successful pair score rolled back")

    monkeypatch.setattr(tasks, "get_db_connection", lambda: Connection())
    monkeypatch.setattr(tasks, "generate_scores_db", lambda *_args, **_kwargs: {
        "total_score": 35, "scores": {"price": {"weight": 1}}})
    monkeypatch.setattr(tasks.reconcile_coach_feed_score, "delay",
                        lambda *args: events.append(("feed", args)))

    result = tasks.build_daily_scores_for_market(42, 11)
    assert result["market_id"] == 11
    assert events == ["commit", "score_written", "commit", ("feed", (42, "BTC", 11)), "close"]
