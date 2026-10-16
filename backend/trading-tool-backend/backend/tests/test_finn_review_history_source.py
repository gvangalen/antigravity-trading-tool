import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_tool_adapters.review_tool_adapter import ReviewToolAdapter


def test_review_history_separates_owner_bot_decisions_from_closed_trade_evidence():
    instant = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    class Repository:
        async def get_bot_history(self, user_id, start, end):
            assert user_id == 42
            assert (end - start).days == 30
            return [{
                "decision_ts": instant,
                "bot_name": "BTC Paper",
                "symbol": "BTC",
                "action": "HOLD",
                "status": "completed",
            }, {
                "decision_ts": instant,
                "bot_name": "ETH Paper",
                "symbol": "ETH",
                "action": "HOLD",
                "status": "completed",
            }]

    adapter = object.__new__(ReviewToolAdapter)
    adapter.repository = Repository()
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
    assert "ETH Paper" not in repr(result["data"].items)
    assert result["data"].closed_trade_status == "no_data"
    assert result["data"].closed_trade_review_ids == []
