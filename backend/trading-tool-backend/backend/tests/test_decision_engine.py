import pytest

from backend.engine.decision_engine import decide_amount
from backend.engine.decision_presets import (
    DCA_CONTRARIAN,
    DCA_TREND_FOLLOWING,
)


def test_fixed_mode():
    setup = {
        "execution_mode": "fixed",
        "base_amount": 100,
    }

    scores = {"market_score": 50, "setup_score": 50}

    assert decide_amount(setup, scores)["final_amount"] == 100.00


def test_contrarian_low_score():
    setup = {
        "execution_mode": "custom",
        "base_amount": 100,
        "decision_curve": DCA_CONTRARIAN,
    }

    scores = {"market_score": 20, "setup_score": 50}
    assert decide_amount(setup, scores)["final_amount"] == 150.00


def test_contrarian_high_score():
    setup = {
        "execution_mode": "custom",
        "base_amount": 100,
        "decision_curve": DCA_CONTRARIAN,
    }

    scores = {"market_score": 90, "setup_score": 50}
    assert decide_amount(setup, scores)["final_amount"] == 5.00


def test_trend_following_strong_market():
    setup = {
        "execution_mode": "custom",
        "base_amount": 100,
        "decision_curve": DCA_TREND_FOLLOWING,
    }

    scores = {"market_score": 80, "setup_score": 50}
    assert decide_amount(setup, scores)["final_amount"] == 140.00


def test_interpolation_mid_point():
    curve = {
        "input": "market_score",
        "points": [
            {"x": 40, "y": 1.2},
            {"x": 60, "y": 1.0},
        ],
    }

    setup = {
        "execution_mode": "custom",
        "base_amount": 100,
        "decision_curve": curve,
    }

    scores = {"market_score": 50, "setup_score": 50}

    # exact midden → 1.1
    assert decide_amount(setup, scores)["final_amount"] == 110.00


def test_invalid_setup_raises():
    with pytest.raises(Exception):
        decide_amount({}, {"market_score": 50})


@pytest.mark.parametrize("market_score,setup_score,expected", [
    (20, 20, 50.0),
    (50, 50, 100.0),
    (80, 80, 150.0),
])
def test_confirmed_dca_score_bands_keep_exact_planned_amount(market_score, setup_score, expected):
    strategy = {
        "setup_type": "dca",
        "execution_mode": "custom",
        "base_amount": 100,
        "dca_amount_semantics": "planned_exact",
        "decision_curve": {
            "input": "benchmark_score",
            "weights_policy": "current_user_preferences",
            "interpolation": "step",
            "points": [
                {"x": 0, "y": 0.5},
                {"x": 40, "y": 1.0},
                {"x": 70, "y": 1.5},
                {"x": 100, "y": 1.5},
            ],
        },
    }

    components = ("market_score", "macro_score", "technical_score")
    result = decide_amount(strategy, {
        **{key: market_score for key in components},
        "setup_score": setup_score,
        "_benchmark_weights": {key: 1/3 for key in components},
        "_source_available": {key: True for key in components},
    })

    assert result["sized_amount"] == result["final_amount"] == expected


def test_previous_market_only_smart_dca_curve_cannot_size_a_purchase():
    setup = {
        "setup_type": "dca", "execution_mode": "custom", "base_amount": 100,
        "dca_amount_semantics": "planned_exact",
        "decision_curve": {
            "input": "market_score", "interpolation": "step",
            "points": [{"x": 0, "y": 0.5}, {"x": 100, "y": 1.5}],
        },
    }
    with pytest.raises(Exception, match="requires the total benchmark"):
        decide_amount(setup, {"market_score": 80, "setup_score": 80})


def test_confirmed_fixed_dca_does_not_change_with_setup_score():
    strategy = {"setup_type": "dca", "execution_mode": "fixed", "base_amount": 100,
                "dca_amount_semantics": "planned_exact"}

    assert decide_amount(strategy, {"market_score": 20, "setup_score": 20})["final_amount"] == 100
    assert decide_amount(strategy, {"market_score": 80, "setup_score": 80})["final_amount"] == 100
