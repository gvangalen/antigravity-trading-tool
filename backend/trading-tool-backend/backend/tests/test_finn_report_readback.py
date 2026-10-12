"""The coach can compare a saved report with newer Score 2.0 facts."""

import asyncio
import json
from datetime import date, datetime, timezone

from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_tool_adapters.report_tool_adapter import ReportToolAdapter


def test_latest_report_read_exposes_saved_scores_and_source_moments():
    snapshot = {
        "observed_at": "2026-10-12T08:15:00+00:00",
        "assets": [
            {"symbol": "ETH", "reported_scores": {
                "market_score": 50, "macro_score": 20, "technical_score": 40,
            }, "component_source_observed_at": {
                "market": {"Price": "2026-10-12T07:20:00+00:00"},
            }},
            {"symbol": "AAPL", "reported_scores": {
                "market_score": None, "macro_score": None, "technical_score": None,
            }},
        ],
    }
    row = {
        "report_date": date(2026, 10, 12),
        "generated_at": datetime(2026, 10, 12, 8, 16, tzinfo=timezone.utc),
        "market_score": None, "macro_score": None, "technical_score": None,
        "setup_score": 74,
        "score_source_snapshot": json.dumps(snapshot),
        "best_setup": {"name": "ETH Base", "score": 74, "symbol": "ETH"},
        "top_setups": [{"name": "ETH Base", "score": 74, "symbol": "ETH"}],
    }
    adapter = ReportToolAdapter(session=None)

    class Reports:
        async def get_latest_report(self, user_id, table_name):
            assert user_id == 7
            assert table_name == "daily_reports"
            return row

    adapter.repository = Reports()
    result = asyncio.run(adapter.execute(user_id=7, asset="ETH", selector={}))
    data = result["data"].dict()
    assert data["score_source_snapshot"] == snapshot
    assert data["setup_score"] == 74
    assert data["best_setup"]["name"] == "ETH Base"
    assert data["market_score"] is None  # Multi-asset report has no global market score.
    assert data["symbol"] is None  # A global report cannot be attributed to the active asset.

    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts(data, "read_latest_report")
    assert facts["score_source_snapshot"]["assets"][0]["reported_scores"]["market_score"] == 50
    assert facts["score_source_snapshot"]["assets"][1]["reported_scores"]["market_score"] is None
    assert facts["generated_at"] == row["generated_at"]
