from __future__ import annotations

import asyncio
from datetime import date, timedelta

from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter


def test_score_adapter_reads_latest_saved_report_with_its_actual_date():
    latest_date = date.today() - timedelta(days=2)

    class Repository:
        async def fetch_daily_scores_batch(self, user_id, symbols):
            assert user_id == 17
            assert symbols == ["BTC"]
            return {"BTC": {
                "report_date": latest_date,
                "market_score": 100,
                "macro_score": 100,
                "technical_score": 75,
                "setup_score": 99,
            }}

    adapter = object.__new__(ScoreToolAdapter)
    adapter.repository = Repository()

    result = asyncio.run(adapter.execute(user_id=17, asset="BTC"))

    assert result["as_of"] == latest_date
    assert result["data"].daily_scores.report_date == latest_date
    assert result["data"].daily_scores.market_score == 100
    assert result["data"].daily_scores.macro_score == 100
    assert result["data"].daily_scores.technical_score == 75
    assert "setup_score" not in result["data"].daily_scores.dict()
