import asyncio

from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter


def test_linked_strategy_evidence_exposes_the_confirmed_smart_dca_rule():
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Smart",
        "base_amount": 100,
        "dca_amount_mode": "score_bands", "score_source": "market_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    data = asyncio.run(StrategyToolAdapter().execute(
        strategy={
            "id": 12, "setup_id": 11, "name": "BTC Smart Strategy",
            "setup_type": "dca", "execution_mode": "custom",
            "base_amount": strategy["base_amount"],
            "decision_curve": strategy["decision_curve"],
            "data": strategy,
        },
        resolution_source="setup_id",
    ))["data"]

    assert data.dca_amount_mode == "score_bands"
    assert data.score_source == "market_score"
    assert (data.low_threshold, data.high_threshold) == (40, 70)
    assert (data.low_score_percent, data.mid_score_percent, data.high_score_percent) == (50, 100, 150)
