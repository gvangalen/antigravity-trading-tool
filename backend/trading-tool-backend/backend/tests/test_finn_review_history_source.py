import asyncio
from datetime import datetime, timezone

from backend.services.finn_v2_tool_adapters.review_tool_adapter import ReviewToolAdapter


def test_review_history_reads_owner_scoped_bot_decisions_not_legacy_reflections():
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

    result = asyncio.run(adapter.execute(user_id=42, asset="BTC"))

    assert result["source"] == "bot_decisions"
    assert result["as_of"] == instant
    assert result["data"].items == [
        "2026-10-09 12:00:00+00:00: bot BTC Paper (BTC) decision HOLD (status: completed)"
    ]
