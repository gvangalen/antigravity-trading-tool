"""The coach can compare a saved report with newer Score 2.0 facts."""

import asyncio
import json
from datetime import date, datetime, timezone
import pytest

from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_tool_adapters.report_tool_adapter import ReportToolAdapter
from backend.services.finn_v2_tool_adapters.score_tool_adapter import ScoreToolAdapter


def test_dated_report_read_uses_owner_date_and_rejects_other_asset():
    adapter = ReportToolAdapter(session=None)
    yesterday = {"report_date": date(2026, 11, 9), "score_source_snapshot": {
        "assets": [{"symbol": "AAPL", "market_snapshot": {
            "price": 351.19, "quote_currency": "USD",
        }}],
    }}

    class Reports:
        async def get_latest_report(self, user_id, table_name):
            raise AssertionError("must not silently use today's report")

        async def get_report_by_date(self, user_id, table_name, report_date):
            assert (user_id, table_name, report_date) == (7, "daily_reports", date(2026, 11, 9))
            return yesterday

    adapter.repository = Reports()
    result = asyncio.run(adapter.execute(
        user_id=7, asset="AAPL", selector={"report_date": "2026-11-09"},
    ))
    assert result["data"].report_date == date(2026, 11, 9)
    assert result["data"].score_source_snapshot["assets"][0]["symbol"] == "AAPL"
    with pytest.raises(LookupError, match="report_asset_not_found"):
        asyncio.run(adapter.execute(
            user_id=7, asset="BTC", selector={"report_date": "2026-11-09"},
        ))


def test_latest_report_read_exposes_saved_scores_and_source_moments():
    snapshot = {
        "observed_at": "2026-10-12T08:15:00+00:00",
        "assets": [
            {"symbol": "ETH", "reported_scores": {
                "market_score": 50, "macro_score": 20, "technical_score": 40,
            }, "market_snapshot": {"as_of": "2026-10-12T07:20:00+00:00"},
            "component_source_observed_at": {
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
    assert data["score_source_snapshot"]["assets"][0]["market_snapshot"] == {
        "as_of": "2026-10-12T07:20:00+00:00",
        "source_observed_at_amsterdam": "2026-10-12 09:20:00 CEST",
    }
    assert data["setup_score"] == 74
    assert data["best_setup"]["name"] == "ETH Base"
    assert data["market_score"] is None  # Multi-asset report has no global market score.
    assert data["symbol"] is None  # A global report cannot be attributed to the active asset.
    assert data["generated_at_amsterdam"] == "2026-10-12 10:16:00 CEST"

    facts = FinnV2ReasoningContextService(session=object())._sanitize_facts(data, "read_latest_report")
    assert facts["score_source_snapshot"]["assets"][0]["reported_scores"]["market_score"] == 50
    assert facts["score_source_snapshot"]["assets"][1]["reported_scores"]["market_score"] is None
    assert facts["generated_at"] == row["generated_at"]
    assert facts["generated_at_amsterdam"] == "2026-10-12 10:16:00 CEST"


def test_later_live_score_change_does_not_rewrite_saved_report_snapshot():
    stored = {
        "report_date": date(2026, 10, 12),
        "generated_at": datetime(2026, 10, 12, 8, 16, tzinfo=timezone.utc),
        "score_source_snapshot": {"observed_at": "2026-10-12T08:15:00+00:00", "assets": [
            {"symbol": "ETH", "reported_scores": {"market_score": 50,
             "macro_score": 20, "technical_score": 40}}]},
    }
    live = {"symbol": "ETH", "as_of": "2026-10-12", "source_status": "available",
            "benchmark_score": 50, "benchmark_weights": {},
            "reported_scores": {"market_score": 50, "macro_score": 20,
                                "technical_score": 40},
            "component_source_status": {"market_score": "fresh",
                                        "macro_score": "fresh", "technical_score": "fresh"}}

    class Reports:
        async def get_latest_report(self, user_id, table_name):
            assert (user_id, table_name) == (7, "daily_reports")
            return stored

    class LiveContext:
        async def benchmark_for_asset(self, user_id, asset, setups):
            assert (user_id, asset, setups) == (7, "ETH", [])
            return live

    report_adapter = ReportToolAdapter(session=None)
    report_adapter.repository = Reports()
    score_adapter = ScoreToolAdapter(session=None)
    score_adapter.context = LiveContext()

    first = asyncio.run(report_adapter.execute(user_id=7, asset="ETH", selector={}))
    assert first["data"].score_source_snapshot["assets"][0]["reported_scores"]["market_score"] == 50
    live["reported_scores"] = {**live["reported_scores"], "market_score": 80}
    live["benchmark_score"] = 60
    current = asyncio.run(score_adapter.execute(user_id=7, asset="ETH"))
    second = asyncio.run(report_adapter.execute(user_id=7, asset="ETH", selector={}))
    assert current["data"].reported_scores["market_score"] == 80
    assert second["data"].score_source_snapshot["assets"][0]["reported_scores"]["market_score"] == 50
    assert second["data"].score_source_snapshot["observed_at"] == "2026-10-12T08:15:00+00:00"
