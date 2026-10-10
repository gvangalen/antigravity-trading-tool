import pytest
from datetime import date

from backend.domain.finn_dca_plan_contract import (
    split_confirmed_dca_plan, dca_due_on_date, benchmark_score, normalize_benchmark_weights,
    is_confirmed_dca_amount_rule,
)
from backend.engine.decision_engine import decide_amount
from backend.ai_agents.trading_bot_agent import _get_current_benchmark_weights
from backend.services.finn_v2_tool_adapters.strategy_tool_adapter import StrategyToolAdapter
import asyncio


def _schedule():
    return {
        "name": "BTC maandag DCA", "symbol": "BTC", "setup_type": "dca",
        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": "monday",
    }


def test_exact_amount_marker_requires_the_canonical_saved_rule():
    _, fixed = split_confirmed_dca_plan({**_schedule(), "dca_amount_mode": "fixed", "base_amount": 100})
    _, smart = split_confirmed_dca_plan({
        **_schedule(), "dca_amount_mode": "score_bands", "base_amount": 100,
        "score_source": "benchmark_score", "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    assert is_confirmed_dca_amount_rule({**fixed, "setup_type": "dca"})
    assert is_confirmed_dca_amount_rule({**smart, "setup_type": "dca"})
    assert not is_confirmed_dca_amount_rule({**fixed, "setup_type": "dca", "base_amount": 0})
    assert not is_confirmed_dca_amount_rule({**smart, "setup_type": "dca", "decision_curve": {"input": "market_score"}})
    assert not is_confirmed_dca_amount_rule({**smart, "setup_type": "trade"})


def test_fixed_dca_splits_schedule_and_exact_strategy_amount():
    setup, strategy = split_confirmed_dca_plan({
        **_schedule(), "dca_amount_mode": "fixed", "base_amount": 100,
    })

    assert setup["dca_day"] == "monday"
    assert "base_amount" not in setup
    assert strategy["execution_mode"] == "fixed"
    assert strategy["base_amount"] == 100
    assert decide_amount({**strategy, "setup_type": "dca"},
                         {"market_score": 20, "setup_score": 20})["final_amount"] == 100


def test_smart_dca_splits_visible_tiers_into_discrete_engine_curve():
    setup, strategy = split_confirmed_dca_plan({
        **_schedule(), "dca_amount_mode": "score_bands",
        "base_amount": 100,
        "score_source": "benchmark_score", "low_threshold": 40,
        "high_threshold": 70, "low_score_percent": 50,
        "mid_score_percent": 100, "high_score_percent": 150,
    })

    assert "score_source" not in setup
    assert strategy["execution_mode"] == "custom"
    assert strategy["decision_curve"]["input"] == "benchmark_score"
    weights = normalize_benchmark_weights({})
    for score, amount in ((0, 50), (39.9, 50), (40, 100),
                          (69.9, 100), (70, 150), (100, 150)):
        result = decide_amount({**strategy, "setup_type": "dca"},
                               {"market_score": score, "macro_score": score,
                                "technical_score": score, "setup_score": score,
                                "_benchmark_weights": weights,
                                "_source_available": {key: True for key in weights}})
        assert result["final_amount"] == amount


def test_saved_smart_dca_readback_uses_engine_at_exact_high_threshold():
    _, strategy = split_confirmed_dca_plan({
        **_schedule(), "dca_amount_mode": "score_bands", "base_amount": 75,
        "score_source": "benchmark_score", "low_threshold": 40,
        "high_threshold": 70, "low_score_percent": 80,
        "mid_score_percent": 100, "high_score_percent": 120,
    })
    saved = {**strategy, "id": 51, "setup_id": 9, "name": "BTC Smart DCA",
             "data": {"dca_amount_semantics": "planned_exact",
                      "decision_curve": strategy["decision_curve"]}}
    readback = asyncio.run(StrategyToolAdapter().execute(
        strategy=saved, resolution_source="explicit_name",
    ))["data"]
    bands = readback.dca_score_bands
    assert [(row["from_score_inclusive"], row["to_score_exclusive"], row["planned_amount"])
            for row in bands] == [(0, 40, 60), (40, 70, 75), (70, None, 90)]
    weights = normalize_benchmark_weights({})
    actual = decide_amount({**strategy, "setup_type": "dca"}, {
        "market_score": 70, "macro_score": 70, "technical_score": 70,
        "_benchmark_weights": weights,
        "_source_available": {key: True for key in weights},
    })
    assert actual["final_amount"] == bands[2]["planned_amount"] == 90


@pytest.mark.parametrize("overrides", [
    {"score_source": None},
    {"score_source": "market_score"},
    {"low_threshold": None},
    {"low_threshold": 70, "high_threshold": 40},
    {"low_score_percent": 0},
    {"low_score_percent": 180},
    {"min_investment": 75},
])
def test_smart_dca_cannot_confirm_missing_or_conflicting_amount_rule(overrides):
    fields = {
        **_schedule(), "dca_amount_mode": "score_bands",
        "base_amount": 100,
        "score_source": "benchmark_score", "low_threshold": 40,
        "high_threshold": 70, "low_score_percent": 50,
        "mid_score_percent": 100, "high_score_percent": 150,
        **overrides,
    }

    with pytest.raises(ValueError):
        split_confirmed_dca_plan(fields)


def test_dca_cadence_is_evaluated_from_the_saved_setup_date():
    monday = date(2026, 10, 5)
    assert dca_due_on_date({"dca_frequency": "weekly", "dca_day": "monday"}, monday)
    assert dca_due_on_date({"dca_frequency": "weekly", "dca_day": "1"}, monday)
    assert not dca_due_on_date({"dca_frequency": "weekly", "dca_day": "1"}, date(2026, 10, 6))
    assert not dca_due_on_date({"dca_frequency": "weekly", "dca_day": "monday"}, date(2026, 10, 6))
    assert dca_due_on_date({"dca_frequency": "monthly", "dca_month_day": "15"}, date(2026, 10, 15))
    assert not dca_due_on_date({"dca_frequency": "monthly", "dca_month_day": "15"}, monday)
    assert dca_due_on_date({"dca_frequency": "daily"}, monday)
    assert not dca_due_on_date({}, monday)


def test_benchmark_requires_all_three_scores_and_uses_current_normalized_weights():
    scores = {"market_score": 20, "macro_score": 80, "technical_score": 80}
    available = {key: True for key in scores}
    equal = normalize_benchmark_weights({})
    assert benchmark_score(scores, equal, available) == 60
    market_heavy = normalize_benchmark_weights({"market": 0.8, "macro": 0.1, "technical": 0.1})
    assert benchmark_score(scores, market_heavy, available) == 32
    assert benchmark_score(scores, equal, {**available, "macro_score": False}) is None
    assert normalize_benchmark_weights({"market": float("nan")}) is None


def test_benchmark_plan_keeps_weight_policy_instead_of_a_weight_snapshot():
    _, strategy = split_confirmed_dca_plan({
        **_schedule(), "dca_amount_mode": "score_bands", "base_amount": 100,
        "score_source": "benchmark_score", "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    curve = strategy["decision_curve"]
    assert curve["input"] == "benchmark_score"
    assert curve["weights_policy"] == "current_user_preferences"
    assert "weights" not in curve


def test_benchmark_weight_loader_prefers_user_settings_then_asset_master_score():
    class Connection:
        def __init__(self, preferences):
            self.preferences = preferences
            self.queries = []

        def cursor(self):
            return self

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params):
            self.queries.append((query, params))

        def fetchone(self):
            query, _ = self.queries[-1]
            if "FROM users" in query:
                return ({"intelligence_weights": self.preferences},)
            return ({"weights": {"market": 0.2, "macro": 0.3, "technical": 0.5, "setup": 0.1}},)

    custom = Connection({"market": 0.8, "macro": 0.1, "technical": 0.1})
    weights, source = _get_current_benchmark_weights(custom, 7, "AAPL")
    assert source == "user_preferences"
    assert weights["market_score"] == 0.8
    assert len(custom.queries) == 1

    master = Connection({})
    weights, source = _get_current_benchmark_weights(master, 7, "AAPL")
    assert source == "equal_default"
    assert all(abs(value - 1 / 3) < 1e-9 for value in weights.values())
    assert len(master.queries) == 1
