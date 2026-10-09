"""Exercise the confirmed score policy through the paper bot's decision path."""

import pytest
import json
from datetime import date

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


def test_fixed_dca_with_unknown_scores_keeps_amount_without_fake_score(paper_engines):
    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "BTC Fixed",
        "dca_amount_mode": "fixed", "base_amount": 100,
    })
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={**strategy, "setup_type": "dca", "symbol": "BTC"},
        scores={"market_score": None, "macro_score": None, "technical_score": None,
                "setup_score": None,
                "_source_available": {key: False for key in
                                      ("market_score", "macro_score", "technical_score", "setup_score")}},
        portfolio_context={"active_strategy": {"setup_type": "dca"}},
        backtest_mode=True,
    )
    assert result["action"] == "buy"
    assert result["amount_eur"] == 100
    assert result["debug"]["scores"]["market_score"] is None
    assert result["trade_context"]["setup_score_reference"] is None
    assert result["market_pressure"] is None


def test_trade_with_unknown_market_score_holds_without_a_weak_score_claim(paper_engines):
    result = bot_brain.run_bot_brain(
        user_id=1,
        setup={"setup_type": "trade", "symbol": "BTC", "execution_mode": "fixed",
               "base_amount": 100},
        scores={"market_score": None, "macro_score": 60, "technical_score": 60,
                "setup_score": None,
                "_source_available": {"market_score": False, "macro_score": True,
                                      "technical_score": True, "setup_score": False}},
        portfolio_context={"active_strategy": {
            "setup_type": "trade", "confidence_score": 80,
            "entry": 100, "stop_loss": 90, "targets": [120],
        }, "live_price": 100},
        backtest_mode=True,
    )
    assert result["action"] == "hold"
    assert "unavailable" in result["reason"].lower()
    assert result["debug"]["scores"]["market_score"] is None


def test_persisted_paper_scores_use_verified_benchmark_and_preserve_unknown(monkeypatch):
    from backend.ai_agents.trading_bot_agent import _persist_decision_and_order

    class Cursor:
        def __init__(self):
            self.saved = None

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, params):
            self.saved = json.loads(params[-1])

        def fetchone(self):
            return (12,)

    class Connection:
        def cursor(self):
            return cursor

    cursor = Cursor()
    decision = {"symbol": "BTC", "action": "hold", "amount_eur": 0}
    scores = {
        "macro": None, "technical": 60, "market": 80,
        "_benchmark_weights": {key: 1 / 3 for key in
                               ("macro_score", "technical_score", "market_score")},
        "_source_available": {"macro_score": False, "technical_score": True,
                              "market_score": True},
    }
    _persist_decision_and_order(
        conn=Connection(), user_id=7, bot_id=8, strategy_id=9, setup_id=10,
        report_date=date.today(), decision=decision, scores=scores,
    )
    assert cursor.saved["macro"] is None
    assert cursor.saved["combined"] is None

    # A stale numeric row must remain unknown even if a caller accidentally
    # forwards its raw value into the persistence boundary.
    scores["macro"] = 95
    _persist_decision_and_order(
        conn=Connection(), user_id=7, bot_id=8, strategy_id=9, setup_id=10,
        report_date=date.today(), decision=decision, scores=scores,
    )
    assert cursor.saved["macro"] is None
    assert cursor.saved["combined"] is None

    scores["macro"] = 40
    scores["_source_available"]["macro_score"] = True
    _persist_decision_and_order(
        conn=Connection(), user_id=7, bot_id=8, strategy_id=9, setup_id=10,
        report_date=date.today(), decision=decision, scores=scores,
    )
    assert cursor.saved["combined"] == 60


@pytest.mark.parametrize("available", [False, True])
def test_worker_records_score_2_decision_for_missing_and_complete_sources(monkeypatch, paper_engines, available):
    from backend.ai_agents import trading_bot_agent as worker

    class Connection:
        committed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            pytest.fail("worker unexpectedly rolled back")

        def close(self):
            pass

    conn = Connection()
    monkeypatch.setattr(worker, "get_db_connection", lambda: conn)
    bot = {"bot_id": 8, "strategy_id": 9, "setup_id": 10, "symbol": "BTC",
           "setup_type": "trade", "is_live": False, "budget": {}}
    monkeypatch.setattr(worker, "_get_active_bots", lambda *args: [bot])
    monkeypatch.setattr(worker, "_get_daily_scores", lambda *args: {
        "market": 80 if available else None,
        "macro": 60 if available else None,
        "technical": 60 if available else None, "setup": None,
        "_report_date": date.today().isoformat(),
        "_source_available": {key: available for key in
                              ("market_score", "macro_score", "technical_score", "setup_score")},
    })
    monkeypatch.setattr(worker, "_get_live_price", lambda *args: 100)
    monkeypatch.setattr(worker, "_get_strategy_setup_payload", lambda *args, **kwargs: {
        "setup_type": "trade", "symbol": "BTC", "execution_mode": "fixed", "base_amount": 100,
    })
    monkeypatch.setattr(worker, "_get_current_benchmark_weights", lambda *args: (
        {key: 1 / 3 for key in ("market_score", "macro_score", "technical_score")},
        "equal_default",
    ))
    monkeypatch.setattr(worker, "_get_saved_setup_conditions", lambda *args: {
        "id": 10, "name": "BTC Plan", "symbol": "BTC", "setup_type": "trade",
        "min_market_score": 40,
    })
    monkeypatch.setattr(worker, "_get_saved_strategy_plan", lambda *args: (
        {"entry": 100, "stop_loss": 90, "targets": [120],
         "confidence": args[-1], "reason": "saved_strategy_and_measured_setup_match"}
        if available else None
    ))
    monkeypatch.setattr(worker, "get_bot_portfolio_state", lambda *args: {
        "cash": 1000, "qty": 0, "invested": 0,
    })
    monkeypatch.setattr(worker, "get_today_spent_eur", lambda *args: 0)
    monkeypatch.setattr(worker, "_clear_existing_pending_orders_for_day", lambda **kwargs: None)
    monkeypatch.setattr(worker, "_touch_bot_last_run", lambda **kwargs: None)
    monkeypatch.setattr(worker, "build_order_proposal", lambda **kwargs: None)
    seen = {}

    def persist(**kwargs):
        seen.update(kwargs)
        return 12

    monkeypatch.setattr(worker, "_persist_decision_and_order", persist)
    result = worker.run_trading_bot_agent(user_id=7, report_date=date.today())

    assert result["ok"] is True
    assert conn.committed is True
    assert result["decisions"][0]["action"] == ("buy" if available else "hold")
    assert result["decisions"][0]["execution_status"] == "no_order"
    assert (seen["scores"]["setup"] is not None) is available
    assert seen["scores"]["_setup_match"]["status"] == (
        "matches" if available else "insufficient_data"
    )
