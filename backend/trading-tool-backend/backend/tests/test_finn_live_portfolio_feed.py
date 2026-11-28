import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.schemas.assistant_schema import AssistantPreferenceUpdate
from backend.services.finn_coach_feed_service import FinnCoachFeedService, _fallback


class Rows:
    def __init__(self, *, first=None, all=None):
        self.one = first
        self.rows = all or []

    def mappings(self):
        return self

    def first(self):
        return self.one

    def all(self):
        return self.rows

    def scalar_one(self):
        return self.one


def test_live_cash_alert_setting_is_independent_of_paper():
    request = AssistantPreferenceUpdate(live_cash_alert_below_pct=25,
                                        paper_cash_alert_below_pct=15)
    assert request.live_cash_alert_below_pct == 25
    assert request.paper_cash_alert_below_pct == 15
    with pytest.raises(ValueError):
        AssistantPreferenceUpdate(live_cash_alert_below_pct=100)


def test_confirmed_live_fill_and_complete_broker_balance_create_separate_events(monkeypatch):
    now = datetime.now(timezone.utc)
    order = {"id": 9, "bot_id": 3, "symbol": "BTC", "side": "buy",
             "status": "filled", "updated_at": now - timedelta(minutes=2),
             "executed_qty": 0.01, "ledger_amount_eur": 500,
             "bot_name": "BTC Live"}
    account = {"total_eur": 200, "cash_eur": 190, "position_value_eur": 800,
               "as_of": now, "exchange_name": "bitvavo"}

    async def execute(sql, params):
        query = str(sql)
        assert params == {"user_id": 7}
        if "FROM users" in query:
            return Rows(first={"cash_limit": "25"})
        if "FROM bot_configs" in query:
            return Rows(first=0)
        if "FROM bot_orders" in query and "JOIN bot_executions" not in query:
            return Rows(all=[])
        if "FROM bot_orders" in query:
            assert "execution_environment='live'" in query
            assert "exchange_order_id IS NOT NULL" in query
            assert "JOIN bot_executions" in query
            return Rows(all=[order])
        if "FROM finn_coach_feed_items" in query:
            return Rows(first=None)
        if "UPDATE finn_live_balance_observations" in query:
            return Rows()
        raise AssertionError(query)

    async def balance(session, user_id):
        assert user_id == 7
        return account

    monkeypatch.setattr("backend.services.live_portfolio_allocation_service.read_live_account", balance)
    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(side_effect=["trade", "cash"])
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == ["trade", "cash"]
    trade, alert = [call.kwargs for call in feed.publish.await_args_list]
    assert trade["event_key"] == "live-order:9"
    assert trade["event_type"] == "live_trade_filled"
    assert trade["evidence"]["portfolio_cash_pct"] == 20
    assert trade["evidence"]["amount_eur"] == "500.00"
    assert alert["event_key"] == "portfolio-cash:live"
    assert alert["evidence"]["cash_pct"] == 20
    assert "broker" in _fallback("live_portfolio_cash_low", "Live", alert["evidence"])["nl"]["body"]
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="live-broker-data:account")


def test_live_fill_remains_visible_without_complete_broker_valuation(monkeypatch):
    now = datetime.now(timezone.utc)
    order = {"id": 10, "bot_id": 3, "symbol": "ETH", "side": "sell",
             "status": "filled", "updated_at": now - timedelta(minutes=3),
             "executed_qty": 2, "ledger_amount_eur": 200,
             "bot_name": "ETH Live"}

    async def execute(sql, params):
        query = str(sql)
        if "FROM users" in query:
            return Rows(first={"cash_limit": "25"})
        if "FROM bot_configs" in query:
            return Rows(first=0)
        if "FROM bot_orders" in query and "JOIN bot_executions" not in query:
            return Rows(all=[])
        if "FROM bot_orders" in query:
            return Rows(all=[order])
        if "UPDATE finn_live_balance_observations" in query:
            return Rows()
        raise AssertionError(query)

    async def balance(_session, _user_id):
        return {"total_eur": 200, "cash_eur": 200, "position_value_eur": None,
                "as_of": now, "exchange_name": "bitvavo"}

    monkeypatch.setattr("backend.services.live_portfolio_allocation_service.read_live_account", balance)
    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="trade")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == ["trade"]
    trade = feed.publish.await_args.kwargs
    assert trade["event_type"] == "live_trade_filled"
    assert "portfolio_cash_pct" not in trade["evidence"]
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="live-broker-data:account")


def test_live_cash_alert_resolves_only_on_verified_recovery(monkeypatch):
    now = datetime.now(timezone.utc)

    async def execute(sql, params):
        query = str(sql)
        if "FROM users" in query:
            return Rows(first={"cash_limit": "20"})
        if "FROM bot_configs" in query:
            return Rows(first=0)
        if "FROM bot_orders" in query:
            return Rows(all=[])
        if "FROM finn_coach_feed_items" in query:
            return Rows(first={"status": "read"})
        if "UPDATE finn_live_balance_observations" in query:
            return Rows()
        raise AssertionError(query)

    account = {"total_eur": 300, "cash_eur": 250, "position_value_eur": 700,
               "as_of": now, "exchange_name": "bitvavo"}

    async def balance(_session, _user_id):
        return account

    monkeypatch.setattr("backend.services.live_portfolio_allocation_service.read_live_account", balance)
    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock()
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    assert any(call.kwargs["event_key"] == "portfolio-cash:live"
               for call in feed.resolve.await_args_list)
    feed.publish.assert_not_awaited()

    feed.resolve.reset_mock()
    account["as_of"] = now - timedelta(minutes=15)
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="live-broker-data:account")


def test_uncertain_live_order_is_not_reported_as_fill_and_resolves_on_confirmation():
    now = datetime.now(timezone.utc)
    state = {"status": "unknown_exchange_state"}

    async def execute(sql, _params):
        query = str(sql)
        if "FROM users" in query:
            return Rows(first={"cash_limit": None})
        if "JOIN bot_executions" in query:
            return Rows(all=[])
        if "FROM bot_orders" in query:
            return Rows(all=[{"id": 91, "bot_id": 8, "symbol": "BTC",
                              "bot_name": "Live BTC", "updated_at": now,
                              "status": state["status"]}])
        if "FROM bot_configs" in query:
            return Rows(first=0)
        if "UPDATE finn_live_balance_observations" in query:
            return Rows()
        raise AssertionError(query)

    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="problem")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == ["problem"]
    published = feed.publish.await_args.kwargs
    assert published["event_type"] == "live_order_attention"
    assert published["event_key"] == "live-order-problem:91"
    assert published["evidence"]["order_status"] == "unknown_exchange_state"
    state["status"] = "filled"
    feed.publish.reset_mock()
    feed.resolve.reset_mock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    feed.publish.assert_not_awaited()
    assert any(call.kwargs["event_key"] == "live-order-problem:91"
               for call in feed.resolve.await_args_list)


def test_broker_gap_requires_sustained_failure_and_active_live_bot(monkeypatch):
    now = datetime.now(timezone.utc)
    state = {"first": now, "active": 1, "account": None}

    async def execute(sql, _params):
        query = str(sql)
        if "FROM users" in query:
            return Rows(first={"cash_limit": None})
        if "FROM bot_orders" in query:
            return Rows(all=[])
        if "FROM bot_configs" in query:
            return Rows(first=state["active"])
        if "INSERT INTO finn_live_balance_observations" in query:
            return Rows(first=state["first"])
        if "UPDATE finn_live_balance_observations" in query:
            return Rows()
        raise AssertionError(query)

    async def balance(_session, _user_id):
        return state["account"]

    monkeypatch.setattr("backend.services.live_portfolio_allocation_service.read_live_account", balance)
    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="broker")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    feed.publish.assert_not_awaited()
    state["first"] = now - timedelta(hours=2)
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == ["broker"]
    assert feed.publish.await_args.kwargs["event_type"] == "live_broker_data_blocked"
    state["active"] = 0
    feed.publish.reset_mock()
    feed.resolve.reset_mock()
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    feed.publish.assert_not_awaited()
    feed.resolve.assert_awaited_with(user_id=7, event_key="live-broker-data:account")


def test_trade_review_notification_requires_saved_ready_analysis():
    now = datetime.now(timezone.utc)
    state = {"analysis_status": "ready"}

    async def execute(sql, params):
        assert params == {"review_id": 42, "user_id": 7}
        assert "FROM finn_trade_reviews" in str(sql)
        return Rows(first={"id": 42, "symbol": "BTC",
                           "analysis_status": state["analysis_status"],
                           "has_analysis": True,
                           "analysis_updated_at": now, "exit_at": now})

    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="review")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.publish_trade_review_ready(user_id=7, review_id=42)) == "review"
    assert feed.publish.await_args.kwargs["subject_id"] == "42"
    state["analysis_status"] = "pending"
    assert asyncio.run(feed.publish_trade_review_ready(user_id=7, review_id=42)) is None
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="trade-review:42")
