import asyncio

from backend.services.indicator_impact_preview_service import summarize_impact
from backend.services.indicator_impact_preview_service import IndicatorImpactPreviewService


def test_preview_marks_score_gated_setups_and_bots_pending_without_inventing_score():
    assessment = {
        "benchmark_score": 66.7, "source_status": "available",
        "matches": [
            {"setup_id": 1, "name": "Smart", "status": "matches",
             "conditions": {"benchmark": {"minimum": 61, "maximum": 75}}},
            {"setup_id": 2, "name": "Fixed DCA", "status": "unconfigured",
             "conditions": {}},
        ],
    }
    bots = [
        {"id": 10, "name": "Smart Paper", "is_active": True, "is_live": False,
         "setup_id": 1, "min_benchmark_score": 61, "max_benchmark_score": 75},
        {"id": 11, "name": "Fixed Paper", "is_active": True, "is_live": False,
         "setup_id": 2, "min_benchmark_score": None, "max_benchmark_score": None},
        {"id": 12, "name": "Inactive", "is_active": False, "is_live": False,
         "setup_id": 1, "min_benchmark_score": 61, "max_benchmark_score": 75},
        {"id": 13, "name": "Smart amount", "is_active": True, "is_live": False,
         "setup_id": 2, "min_benchmark_score": None, "max_benchmark_score": None,
         "execution_mode": "custom", "decision_curve": {"input": "benchmark_score"}},
    ]
    preview = summarize_impact(assessment, bots)
    assert preview["simulation_only"] is True
    assert preview["before"]["benchmark_score"] == 66.7
    assert preview["after"]["benchmark_score"] is None
    assert preview["setups"][0]["after_status"] == "pending_score"
    assert preview["setups"][1]["after_status"] == "no_score_condition"
    assert [item["after_status"] for item in preview["bots"]] == [
        "wait_for_fresh_score", "no_score_gate_change", "wait_for_fresh_score",
    ]


def test_pair_preview_reads_only_setups_and_bots_for_selected_market(monkeypatch):
    captured = {}

    class FakeAssessment:
        def __init__(self, session):
            pass

        async def for_asset(self, user_id, symbol, *, market_id=None):
            captured["assessment"] = (user_id, symbol, market_id)
            return {"benchmark_score": 40, "source_status": "available", "matches": []}

    class FakeResult:
        def mappings(self):
            return self

        def all(self):
            return []

    class FakeSession:
        async def execute(self, statement, params):
            captured["sql"] = str(statement)
            captured["params"] = params
            return FakeResult()

    monkeypatch.setattr(
        "backend.services.indicator_impact_preview_service.SetupMarketMatchService",
        FakeAssessment,
    )
    preview = asyncio.run(IndicatorImpactPreviewService(FakeSession()).preview(
        user_id=7, symbol="BTC", category="technical", indicator="rsi", market_id=12))
    assert captured["assessment"] == (7, "BTC", 12)
    assert "st.market_id = :market_id" in captured["sql"]
    assert captured["params"] == {"user_id": 7, "symbol": "BTC", "market_id": 12}
    assert preview["market_id"] == 12
