"""Exercise the confirmed score policy through the paper bot's decision path."""

import pytest

from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
from backend.engine import bot_brain


@pytest.fixture
def paper_engines(monkeypatch):
    monkeypatch.setattr(bot_brain, "get_regime_memory", lambda user_id: None)
    monkeypatch.setattr(bot_brain, "get_market_intelligence", lambda **kwargs: {
        "trend": {}, "state": {
            "market_pressure": 0.8, "transition_risk": 0.1,
        }, "metrics": {},
    })
    monkeypatch.setattr(bot_brain, "apply_guardrails", lambda **kwargs: {
        "allowed": kwargs["proposed_amount_eur"] > 0,
        "adjusted_amount_eur": kwargs["proposed_amount_eur"],
        "warnings": [], "blocked_by": None,
    })
    monkeypatch.setattr(bot_brain, "build_trade_plan", lambda **kwargs: {})


@pytest.mark.parametrize("score,expected", [(20, 50), (50, 100), (80, 150)])
def test_smart_dca_paper_amounts_follow_the_visible_score_bands(paper_engines, score, expected):
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Smart",
        "base_amount": 100,
        "dca_amount_mode": "score_bands", "score_source": "benchmark_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={
            "market_score": score, "macro_score": score, "technical_score": score,
            "setup_score": 80,
            "_benchmark_weights": {key: 1/3 for key in ("market_score", "macro_score", "technical_score")},
            "_source_available": {key: True for key in ("market_score", "macro_score", "technical_score")},
        },
        portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )

    assert result["action"] == "buy"
    assert result["amount_eur"] == expected


def test_smart_dca_missing_score_cannot_turn_placeholder_into_a_buy(paper_engines):
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Smart",
        "base_amount": 100,
        "dca_amount_mode": "score_bands", "score_source": "benchmark_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={
            "market_score": 10, "macro_score": 80, "technical_score": 80,
            "setup_score": 80,
            "_benchmark_weights": {key: 1/3 for key in ("market_score", "macro_score", "technical_score")},
            "_source_available": {"market_score": False, "macro_score": True, "technical_score": True},
        },
        portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )

    assert result["action"] == "hold"
    assert result["amount_eur"] == 0


def test_previous_market_only_smart_dca_plan_holds_even_with_a_valid_market_score(paper_engines):
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={
            "setup_type": "dca", "symbol": "BTC", "execution_mode": "custom",
            "base_amount": 100, "dca_amount_semantics": "planned_exact",
            "decision_curve": {
                "input": "market_score", "interpolation": "step",
                "points": [{"x": 0, "y": 0.5}, {"x": 100, "y": 1.5}],
            },
        },
        scores={
            "market_score": 80, "macro_score": 80, "technical_score": 80,
            "setup_score": 80,
            "_source_available": {"market_score": True, "macro_score": True, "technical_score": True},
        },
        portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )
    assert result["action"] == "hold"
    assert result["amount_eur"] == 0
    assert "total benchmark" in result["reason"]


@pytest.mark.parametrize("weights,expected", [
    ({"market_score": 1/3, "macro_score": 1/3, "technical_score": 1/3}, 100),
    ({"market_score": 0.8, "macro_score": 0.1, "technical_score": 0.1}, 50),
])
def test_benchmark_smart_dca_uses_current_weights(paper_engines, weights, expected):
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Benchmark", "base_amount": 100,
        "dca_amount_mode": "score_bands", "score_source": "benchmark_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    scores = {
        "market_score": 20, "macro_score": 80, "technical_score": 80,
        "setup_score": 80, "_benchmark_weights": weights,
        "_source_available": {key: True for key in weights},
    }
    result = bot_brain.run_bot_brain(
        user_id=1, setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores=scores, portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )
    assert result["action"] == "buy"
    assert result["amount_eur"] == expected
    scores["_source_available"]["technical_score"] = False
    missing = bot_brain.run_bot_brain(
        user_id=1, setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores=scores, portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )
    assert missing["action"] == "hold"
    assert missing["amount_eur"] == 0


def test_confirmed_dca_does_not_buy_if_guardrails_fail(paper_engines, monkeypatch):
    monkeypatch.setattr(bot_brain, "apply_guardrails", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("unavailable")))
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Fixed",
        "dca_amount_mode": "fixed", "base_amount": 100,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={"market_score": 80, "macro_score": 80, "technical_score": 80, "setup_score": 80},
        portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )

    assert result["action"] == "hold"
    assert result["amount_eur"] == 0


def test_confirmed_dca_honors_guardrail_denial_even_if_an_amount_is_returned(paper_engines, monkeypatch):
    monkeypatch.setattr(bot_brain, "apply_guardrails", lambda **kwargs: {
        "allowed": False, "adjusted_amount_eur": kwargs["proposed_amount_eur"],
    })
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Fixed",
        "dca_amount_mode": "fixed", "base_amount": 100,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={"market_score": 80, "macro_score": 80, "technical_score": 80, "setup_score": 80},
        portfolio_context={"active_strategy": {"setup_type": "dca", "confidence_score": 80}},
        backtest_mode=True,
    )

    assert result["action"] == "hold"
    assert result["amount_eur"] == 0


def test_fixed_dca_does_not_treat_missing_macro_score_as_a_defensive_signal(paper_engines, monkeypatch):
    observed = {}

    def guardrails(**kwargs):
        observed.update(kwargs)
        return {"allowed": True, "adjusted_amount_eur": kwargs["proposed_amount_eur"]}

    monkeypatch.setattr(bot_brain, "apply_guardrails", guardrails)
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Fixed",
        "dca_amount_mode": "fixed", "base_amount": 100,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={
            "market_score": 10, "macro_score": 10, "technical_score": 10,
            "setup_score": 10, "_source_available": {"macro_score": False},
        },
        portfolio_context={"active_strategy": {"setup_type": "dca"}},
        backtest_mode=True,
    )

    assert observed["global_macro_score"] is None
    assert result["action"] == "buy"
    assert result["amount_eur"] == 100
