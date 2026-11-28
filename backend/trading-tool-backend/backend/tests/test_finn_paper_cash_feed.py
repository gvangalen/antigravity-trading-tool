import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.schemas.assistant_schema import AssistantPreferenceUpdate
from backend.services.finn_coach_feed_service import FinnCoachFeedService, _fallback


def test_paper_cash_alert_setting_requires_a_valid_percentage():
    assert AssistantPreferenceUpdate(paper_cash_alert_below_pct=20).paper_cash_alert_below_pct == 20
    assert AssistantPreferenceUpdate(paper_cash_alert_below_pct=0).paper_cash_alert_below_pct == 0
    with pytest.raises(ValueError):
        AssistantPreferenceUpdate(paper_cash_alert_below_pct=100)


def test_low_cash_alert_uses_verified_paper_snapshot_and_saved_limit():
    now = datetime.now(timezone.utc)
    snapshot = {"ts": now.replace(minute=0, second=0, microsecond=0),
                "source_min_at": now, "equity_eur": 1000,
                "cash_eur": 150, "covered_bot_count": 2}

    class Rows:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    async def execute(sql, params):
        query = str(sql)
        if "FROM users" in query:
            return Rows({"cash_limit": "20"})
        if "FROM portfolio_value_snapshots_v2" in query:
            return Rows(snapshot)
        if "FROM finn_coach_feed_items" in query:
            return Rows(None)
        raise AssertionError(query)

    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="alert-1")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_paper_cash_alert(user_id=7)) == ["alert-1"]
    alert = feed.publish.await_args.kwargs
    assert alert["event_type"] == "portfolio_cash_low"
    assert alert["subject_type"] == "portfolio"
    assert alert["evidence"]["cash_pct"] == 15
    assert alert["evidence"]["limit_pct"] == 20
    assert "15.0%" in _fallback("portfolio_cash_low", "Paper", alert["evidence"])["nl"]["body"]
    feed.resolve.assert_not_awaited()


def test_paper_cash_alert_resolves_after_recovery_and_rejects_old_valuation():
    now = datetime.now(timezone.utc)
    snapshot = {"ts": now.replace(minute=0, second=0, microsecond=0),
                "source_min_at": now, "equity_eur": 1000,
                "cash_eur": 260, "covered_bot_count": 1}

    class Rows:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    async def execute(sql, params):
        query = str(sql)
        if "FROM users" in query:
            return Rows({"cash_limit": "20"})
        if "FROM portfolio_value_snapshots_v2" in query:
            return Rows(snapshot)
        if "FROM finn_coach_feed_items" in query:
            return Rows({"status": "read"})
        raise AssertionError(query)

    feed = FinnCoachFeedService(SimpleNamespace(execute=execute))
    feed.publish = AsyncMock(return_value="alert-1")
    feed.resolve = AsyncMock()
    assert asyncio.run(feed.reconcile_paper_cash_alert(user_id=7)) == []
    feed.resolve.assert_awaited_once_with(user_id=7, event_key="portfolio-cash:paper")
    feed.publish.assert_not_awaited()

    snapshot["cash_eur"] = 150
    snapshot["source_min_at"] = now - timedelta(hours=2)
    feed.resolve.reset_mock()
    assert asyncio.run(feed.reconcile_paper_cash_alert(user_id=7)) == []
    feed.resolve.assert_not_awaited()
    feed.publish.assert_not_awaited()
