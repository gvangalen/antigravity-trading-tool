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
