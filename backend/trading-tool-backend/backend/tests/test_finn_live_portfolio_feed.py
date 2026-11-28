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
        if "FROM bot_orders" in query:
            assert "execution_environment='live'" in query
            assert "exchange_order_id IS NOT NULL" in query
            assert "JOIN bot_executions" in query
            return Rows(all=[order])
        if "FROM finn_coach_feed_items" in query:
            return Rows(first=None)
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
    feed.resolve.assert_not_awaited()


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
        if "FROM bot_orders" in query:
            return Rows(all=[order])
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
    feed.resolve.assert_not_awaited()


def test_live_cash_alert_resolves_only_on_verified_recovery(monkeypatch):
    now = datetime.now(timezone.utc)

    async def execute(sql, params):
        query = str(sql)
        if "FROM users" in query:
            return Rows(first={"cash_limit": "20"})
        if "FROM bot_orders" in query:
            return Rows(all=[])
        if "FROM finn_coach_feed_items" in query:
            return Rows(first={"status": "read"})
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
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="portfolio-cash:live")
    feed.publish.assert_not_awaited()

    feed.resolve.reset_mock()
    account["as_of"] = now - timedelta(minutes=15)
    assert asyncio.run(feed.reconcile_live_portfolio_events(user_id=7)) == []
    feed.resolve.assert_not_awaited()
