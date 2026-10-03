import pytest
from datetime import date

from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan, dca_due_on_date
from backend.engine.decision_engine import decide_amount


def _schedule():
    return {
        "name": "BTC maandag DCA", "symbol": "BTC", "setup_type": "dca",
        "timeframe": "1D", "dca_frequency": "weekly", "dca_day": "monday",
    }


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
        "score_source": "market_score", "low_threshold": 40,
        "high_threshold": 70, "low_score_percent": 50,
        "mid_score_percent": 100, "high_score_percent": 150,
    })

    assert "score_source" not in setup
    assert strategy["execution_mode"] == "custom"
    assert strategy["decision_curve"]["input"] == "market_score"
    for score, amount in ((0, 50), (39.9, 50), (40, 100),
                          (69.9, 100), (70, 150), (100, 150)):
        result = decide_amount({**strategy, "setup_type": "dca"},
                               {"market_score": score, "setup_score": score})
        assert result["final_amount"] == amount


@pytest.mark.parametrize("overrides", [
    {"score_source": None},
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
        "score_source": "market_score", "low_threshold": 40,
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
