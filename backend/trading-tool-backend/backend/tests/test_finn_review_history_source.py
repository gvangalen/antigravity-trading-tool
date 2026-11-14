import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_tool_adapters.review_tool_adapter import ReviewToolAdapter


def test_review_history_separates_owner_bot_decisions_from_closed_trade_evidence():
    instant = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    class BotHistory:
        async def get_bot_history(self, user_id, days):
            assert user_id == 42
            assert days == 30
            return [{
                "decision_ts": instant,
                "bot_name": "BTC Paper",
                "symbol": "BTC",
                "action": "HOLD",
                "status": "completed",
                "safety_check": {"state": "blocked", "reason_code": "setup_match"},
            }, {
                "decision_ts": instant,
                "bot_name": "ETH Paper",
                "symbol": "ETH",
                "action": "HOLD",
                "status": "completed",
            }]

    adapter = object.__new__(ReviewToolAdapter)
    adapter.bot_service = BotHistory()
    class LatestDecisions:
        async def get_latest_bot_decisions_for_owner(self, user_id):
            assert user_id == 42
            return [{"bot_name": "BTC Paper", "is_live": False, "symbol": "BTC",
                     "action": "HOLD", "status": "completed", "decision_ts": instant},
                    {"bot_name": "AAPL Paper", "is_live": False, "symbol": "AAPL",
                     "action": "HOLD", "status": "completed", "decision_ts": instant}]
    adapter.repository = LatestDecisions()
    from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
    adapter.sources = FinnV2InformationSourceRegistry()
    class ClosedTrades:
        async def recent(self, user_id, *, days, limit, symbol=None):
            assert user_id == 42 and days == 30 and limit == 5 and symbol == "BTC"
            return {"status": "no_data", "coverage": {"trades": 0, "analyzed": 0, "pending": 0, "unavailable": 0}, "reviews": []}

    adapter.closed_trades = ClosedTrades()

    result = asyncio.run(adapter.execute(user_id=42, asset="BTC"))

    assert result["source"] == "bot_decisions_and_finn_trade_reviews"
    assert result["as_of"] == instant
    assert "geen bevestigde gesloten trade" in result["data"].items[0]
    assert "BTC Paper" in result["data"].items[0]
    assert "veiligheidsstatus blocked" in result["data"].items[0]
    assert "ETH Paper" not in repr(result["data"].items)
    assert result["data"].closed_trade_status == "no_data"
    assert result["data"].closed_trade_review_ids == []
    assert len(result["data"].latest_bot_decisions) == 1
    assert result["data"].latest_bot_decisions[0]["decision_at_amsterdam"] == "2026-10-09 14:00:00 CEST"


def test_review_history_keeps_newest_bot_decision_when_many_rows_exist():
    class BotHistory:
        async def get_bot_history(self, user_id, days):
            assert user_id == 42 and days == 30
            return [
                {
                    "decision_ts": datetime(2026, 11, 6, 8, minute, tzinfo=timezone.utc),
                    "bot_name": "Older BTC", "symbol": "BTC",
                    "action": "hold", "status": "planned",
                } for minute in range(25)
            ] + [{
                "decision_ts": datetime(2026, 11, 7, 18, 45, tzinfo=timezone.utc),
                "bot_name": "Latest AAPL", "symbol": "AAPL",
                "action": "hold", "status": "planned",
            }]

    class ClosedTrades:
        async def recent(self, user_id, *, days, limit, symbol=None):
            return {
                "status": "no_data",
                "coverage": {"trades": 0, "analyzed": 0, "pending": 0, "unavailable": 0},
                "reviews": [],
            }

    adapter = object.__new__(ReviewToolAdapter)
    adapter.bot_service = BotHistory()
    class LatestDecisions:
        async def get_latest_bot_decisions_for_owner(self, user_id):
            return []
    adapter.repository = LatestDecisions()
    from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
    adapter.sources = FinnV2InformationSourceRegistry()
    adapter.closed_trades = ClosedTrades()

    result = asyncio.run(adapter.execute(user_id=42))
    assert "Latest AAPL" in result["data"].items[0]
    assert "2026-11-07 19:45:00 CET" in result["data"].items[0]


def test_latest_owner_bot_decisions_do_not_depend_on_active_setup_or_history_window():
    class BotHistory:
        async def get_bot_history(self, user_id, days):
            assert (user_id, days) == (42, 30)
            return []

    class LatestDecisions:
        async def get_latest_bot_decisions_for_owner(self, user_id):
            assert user_id == 42
            return [
                {"bot_name": "BTC Paper", "is_live": False, "symbol": "BTC",
                 "action": "hold", "status": "completed",
                 "decision_ts": datetime(2026, 10, 18, 7, 48, 54, tzinfo=timezone.utc)},
                {"bot_name": "AAPL Paper", "is_live": False, "symbol": "AAPL",
                 "action": "buy", "status": "completed",
                 "decision_ts": datetime(2026, 11, 7, 19, tzinfo=timezone.utc)},
                {"bot_name": "BTC Live", "is_live": True, "symbol": "BTC",
                 "quote_currency": "USDT", "action": "hold", "status": "completed",
                 "decision_ts": datetime(2026, 11, 7, 19, tzinfo=timezone.utc)},
            ]

    class ClosedTrades:
        async def recent(self, user_id, *, days, limit, symbol=None):
            return {"status": "no_data", "coverage": {"trades": 0,
                    "analyzed": 0, "pending": 0, "unavailable": 0}, "reviews": []}

    adapter = object.__new__(ReviewToolAdapter)
    adapter.bot_service = BotHistory()
    adapter.repository = LatestDecisions()
    from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
    adapter.sources = FinnV2InformationSourceRegistry()
    adapter.closed_trades = ClosedTrades()
    result = asyncio.run(adapter.execute(user_id=42, asset="BTC"))
    assert result["data"].latest_bot_decisions[0] == {
        "bot_name": "BTC Paper", "symbol": "BTC", "is_live": False,
        "action": "hold", "persistence_status": "completed",
        "decision_kind": "assessment", "decision_at": "2026-10-18T07:48:54+00:00",
        "decision_at_amsterdam": "2026-10-18 09:48:54 CEST",
    }
    assert len(result["data"].latest_bot_decisions) == 2
    assert result["data"].latest_bot_decisions[1]["pair"] == "BTC/USDT"
    assert result["data"].latest_bot_decisions[1]["is_live"] is True


def test_bot_decision_only_read_survives_unavailable_trade_review_and_legacy_history():
    class UnavailableLegacy:
        async def get_bot_history(self, *_args):
            raise AssertionError("legacy 30-day history must not block latest bot decision")

    class LatestDecisions:
        async def get_latest_bot_decisions_for_owner(self, user_id):
            assert user_id == 42
            return [{"bot_name": "BTC Paper", "is_live": False, "symbol": "BTC",
                     "action": "hold", "status": "planned",
                     "decision_ts": datetime(2026, 10, 18, 7, 48, 54, tzinfo=timezone.utc)}]

    adapter = object.__new__(ReviewToolAdapter)
    adapter.bot_service = UnavailableLegacy()
    adapter.repository = LatestDecisions()
    from backend.domain.finn_v2_source_registry import FinnV2InformationSourceRegistry
    adapter.sources = FinnV2InformationSourceRegistry()
    adapter.closed_trades = UnavailableLegacy()

    result = asyncio.run(adapter.execute(
        user_id=42, asset="BTC", selector={"_latest_bot_decisions_only": True},
    ))
    assert result["source"] == "bot_decisions"
    assert result["data"].latest_bot_decisions[0]["decision_at_amsterdam"] == "2026-10-18 09:48:54 CEST"
