"""One source fixture through score persistence, setup match and paper sizing."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.engine import trading_bot_execution as paper_worker
from backend.celery_task import store_daily_scores_task
from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
from backend.domain.setup_market_match import match_setup_from_daily_scores
from backend.engine import bot_brain
from backend.utils import scoring_utils
from backend.utils import macro_interpreter, market_interpreter, technical_interpreter


@pytest.mark.parametrize(
    ("status", "setup", "conditions", "expected_action"),
    [
        ("matches", {"setup_type": "dca", "execution_mode": "custom"}, True, "buy"),
        ("outside_conditions", {"setup_type": "dca", "execution_mode": "custom"}, True, "hold"),
        ("outside_conditions", {"setup_type": "dca", "execution_mode": "fixed"}, True, "hold"),
        ("unconfigured", {"setup_type": "trade", "execution_mode": "fixed"}, False, "hold"),
        ("unconfigured", {"setup_type": "dca", "execution_mode": "fixed"}, False, "buy"),
        ("insufficient_data", {"setup_type": "dca", "execution_mode": "custom"}, True, "hold"),
        ("insufficient_data", {"setup_type": "dca", "execution_mode": "fixed"}, True, "hold"),
        ("insufficient_data", {"setup_type": "trade", "execution_mode": "fixed"}, True, "hold"),
    ],
)
def test_paper_buy_respects_measured_setup_match_without_disabling_fixed_dca(
    status, setup, conditions, expected_action,
):
    brain = {"action": "buy", "amount_eur": 100, "position_size": 1,
             "debug": {"suggested_amount": 100}}
    result = paper_worker._enforce_setup_match_on_buy(
        brain, {"status": status, "conditions": {"macro": {"min": 30}} if conditions else {}}, setup,
    )
    assert result["action"] == expected_action
    if expected_action == "hold":
        assert result["amount_eur"] == 0
        assert paper_worker.build_order_proposal(
            bot={"budget": {}}, decision=result, today_spent_eur=0,
            total_balance_eur=1000, live_price=100,
        ) is None
    assert brain["action"] == "buy"


@pytest.mark.parametrize(
    ("minimum", "expected_status", "expected_action"),
    [(None, "unconfigured", "buy"), (30, "insufficient_data", "hold")],
)
def test_fixed_dca_missing_macro_follows_saved_score_conditions(
    minimum, expected_status, expected_action,
):
    setup = {"name": "ETH fixed", "symbol": "ETH", "setup_type": "dca"}
    if minimum is not None:
        setup["min_benchmark_score"] = minimum
    match = match_setup_from_daily_scores(
        setup, {"market": 40, "macro": None, "technical": 40},
        {"market_score": 1 / 3, "macro_score": 1 / 3, "technical_score": 1 / 3},
    )
    assert match["status"] == expected_status
    decision = paper_worker._enforce_setup_match_on_buy(
        {"action": "buy", "amount_eur": 75, "position_size": 1}, match,
        {"setup_type": "dca", "execution_mode": "fixed"},
    )
    assert decision["action"] == expected_action
    if expected_action == "hold":
        assert paper_worker.build_order_proposal(
            bot={"budget": {}}, decision=decision, today_spent_eur=0,
            total_balance_eur=1000, live_price=100,
        ) is None


def test_setup_match_gate_never_blocks_a_sell_exit():
    brain = {"action": "sell", "amount_eur": 100}
    assert paper_worker._enforce_setup_match_on_buy(
        brain, {"status": "outside_conditions"}, {"setup_type": "trade"},
    ) == brain


class _SourceStore:
    def __init__(self, *, missing=None, stale=None):
        now = datetime.now(timezone.utc)
        self.now = now
        self.names = {"macro": "dxy", "technical": "rsi", "market": "price"}
        self.values = {"macro": 102.2, "technical": 55, "market": 76000}
        self.observed = {category: now - timedelta(hours=1) for category in self.names}
        if missing:
            self.observed[missing] = None
        if stale:
            self.observed[stale] = now - timedelta(days=30)
        self.daily = None

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class _Cursor:
    def __init__(self, store):
        self.store = store
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        if "SELECT symbol FROM watchlists" in sql:
            self.rows = [("ETH",)]
        elif "INSERT INTO daily_scores" in sql:
            self.store.daily = {
                "report_date": date.today(), "macro_score": params[2],
                "technical_score": params[3], "market_score": params[4],
                "calculated_at": self.store.now,
                "indicator_evidence": json.loads(params[-1]),
            }
            self.rows = []
        elif "SELECT indicator FROM user_indicator_configs" in sql:
            self.rows = [(self.store.names[params[1]],)]
        elif "SELECT indicator, updated_at FROM user_indicator_configs" in sql:
            self.rows = [(self.store.names[params[1]], self.store.now - timedelta(hours=2))]
        elif "SELECT DISTINCT ON" in sql:
            category = next(key for key, table in (
                ("macro", "macro_data"), ("technical", "technical_indicators"),
                ("market", "market_data_indicators"),
            ) if f"FROM {table}" in sql)
            observed = self.store.observed[category]
            self.rows = [(self.store.names[category], self.store.values[category], observed)] if observed else []
        elif "SELECT macro_score, technical_score, market_score, calculated_at" in sql:
            row = self.store.daily
            self.rows = [(row["macro_score"], row["technical_score"], row["market_score"],
                          row["calculated_at"], row["indicator_evidence"])] if row else []
        elif "pg_advisory_lock" in sql or "pg_advisory_xact_lock" in sql or "SELECT 1 FROM bot_decisions" in sql:
            self.rows = []
        else:
            raise AssertionError(f"Unexpected score-chain query: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


@pytest.mark.parametrize("mode", ["manual", "semi-auto", "semi", "unknown"])
def test_auto_executor_rejects_unapproved_bot_modes(mode):
    with pytest.raises(RuntimeError, match="requires auto mode"):
        paper_worker._auto_execute_decision(
            conn=None, user_id=7, bot_id=11, decision_id=13,
            order={"symbol": "ETH", "side": "buy", "estimated_price": 100,
                   "estimated_qty": 1},
            is_live=True, mode=mode,
        )


@pytest.mark.parametrize(
    ("saved_bot", "error"),
    [
        (None, "active auto bot"),
        (("manual", True, True), "active auto bot"),
        (("semi-auto", True, True), "active auto bot"),
        (("auto", True, False), "active auto bot"),
        (("auto", False, True), "environment changed"),
    ],
)
def test_auto_executor_rechecks_current_bot_before_exchange(saved_bot, error):
    class BotCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, params):
            if "pg_advisory_xact_lock" in statement:
                assert params == (7, 0)
                self.row = None
            elif "FROM bot_orders" in statement:
                assert params == (7, 11, 13)
                self.row = None
            else:
                assert "FOR UPDATE" in statement
                assert params == (11, 7)
                self.row = saved_bot

        def fetchone(self):
            return self.row

    class BotConnection:
        def cursor(self):
            return BotCursor()

    with pytest.raises(RuntimeError, match=error):
        paper_worker._auto_execute_decision(
            conn=BotConnection(), user_id=7, bot_id=11, decision_id=13,
            order={"symbol": "ETH", "side": "buy", "estimated_price": 100,
                   "estimated_qty": 1},
            is_live=True, mode="auto",
        )


def test_legacy_manual_live_bot_decision_cannot_book_unconfirmed_fill(monkeypatch):
    class BotCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, statement, params):
            assert "FOR UPDATE" in statement
            assert params == (11, 7)

        def fetchone(self):
            return True, True

    class BotConnection:
        def cursor(self):
            return BotCursor()

    monkeypatch.setattr(paper_worker, "_claim_bot_decision_for_execution", lambda **_: pytest.fail("decision claimed"))
    monkeypatch.setattr(paper_worker, "_execute_on_exchange_sync", lambda *_: pytest.fail("exchange order sent"))
    with pytest.raises(RuntimeError, match="bevestigde exchange-fill"):
        paper_worker.execute_manual_decision(
            conn=BotConnection(), user_id=7, bot_id=11, decision_id=13,
        )


@pytest.mark.parametrize("unavailable", [None, "missing", "stale", "outside"])
@pytest.mark.parametrize("mode", ["manual", "semi-auto", "auto"])
def test_source_to_score2_to_setup_match_to_paper_amount(monkeypatch, unavailable, mode):
    monkeypatch.setattr(store_daily_scores_task.reconcile_coach_feed_score, "delay", lambda *_: None)
    feed_decisions = []
    monkeypatch.setattr(store_daily_scores_task.publish_coach_bot_decision, "delay",
                        lambda *args: feed_decisions.append(args))
    store = _SourceStore(
        missing="technical" if unavailable == "missing" else None,
        stale="technical" if unavailable == "stale" else None,
    )
    monkeypatch.setattr(scoring_utils, "get_db_connection", lambda: store)
    monkeypatch.setattr(store_daily_scores_task, "get_db_connection", lambda: store)
    monkeypatch.setattr(market_interpreter, "normalize_market_value_with_history", lambda *args: args[-1])
    monkeypatch.setattr(macro_interpreter, "normalize_macro_value_with_history", lambda *args: args[-1])
    monkeypatch.setattr(technical_interpreter, "normalize_technical_value", lambda _name, value: value)
    scores_by_category = {"market": 80, "macro": 70, "technical": 60}
    monkeypatch.setattr(scoring_utils, "score_indicator", lambda **kwargs: {
        "score": scores_by_category[kwargs["category"]], "weight": 1,
        "trend": "neutral", "interpretation": "fixture", "action": "wait",
        "score_mode": "standard", "rule_origin": "system_template",
    })

    store_daily_scores_task.build_daily_scores_for_user(7)
    saved = store.daily
    assert saved is not None
    assert saved["market_score"] == 80 and saved["macro_score"] == 70
    assert saved["technical_score"] == (None if unavailable in {"missing", "stale"} else 60)

    verified = paper_worker._get_daily_scores(store, 7, date.today(), "ETH")
    weights = {key: 1 / 3 for key in ("market_score", "macro_score", "technical_score")}
    setup = {"id": 9, "name": "ETH Smart", "symbol": "ETH", "setup_type": "dca",
             "min_benchmark_score": 90 if unavailable == "outside" else 70}
    match = match_setup_from_daily_scores(setup, verified, weights)
    expected_match_status = (
        "insufficient_data" if unavailable in {"missing", "stale"}
        else "outside_conditions" if unavailable == "outside" else "matches"
    )
    assert match["status"] == expected_match_status
    if unavailable in {"missing", "stale"}:
        assert match["score"] is None
    else:
        assert match["score"] is not None

    _, strategy = split_confirmed_dca_plan({
        "setup_type": "dca", "name": "ETH Smart", "base_amount": 100,
        "dca_amount_mode": "score_bands", "score_source": "benchmark_score",
        "low_threshold": 40, "high_threshold": 70,
        "low_score_percent": 50, "mid_score_percent": 100, "high_score_percent": 150,
    })
    monkeypatch.setattr(bot_brain, "get_regime_memory", lambda _user_id: None)
    monkeypatch.setattr(bot_brain, "get_market_intelligence", lambda **_: {
        "trend": {}, "state": {"market_pressure": 0.8, "transition_risk": 0.1}, "metrics": {},
    })
    monkeypatch.setattr(bot_brain, "apply_guardrails", lambda **kwargs: {
        "allowed": True, "adjusted_amount_eur": kwargs["proposed_amount_eur"],
        "warnings": [], "blocked_by": None,
    })
    monkeypatch.setattr(bot_brain, "build_trade_plan", lambda **_: {})
    decision = bot_brain.run_bot_brain(
        user_id=7, setup={**strategy, "setup_type": "dca", "symbol": "ETH"},
        scores={"market_score": verified["market"], "macro_score": verified["macro"],
                "technical_score": verified["technical"], "setup_score": match["score"],
                "_source_available": verified["_source_available"],
                "_benchmark_weights": weights},
        portfolio_context={"active_strategy": {"setup_type": "dca"}},
        backtest_mode=True,
    )
    assert decision["action"] == ("hold" if unavailable in {"missing", "stale"} else "buy")
    assert decision["amount_eur"] == (0 if unavailable in {"missing", "stale"} else 150)

    # Exercise the worker's actual paper decision path with the same saved
    # score row. No order is created; only the decision payload is inspected.
    monkeypatch.setattr(paper_worker, "get_db_connection", lambda: store)
    monkeypatch.setattr(paper_worker, "_get_active_bots", lambda *_: [{
        "bot_id": 11, "strategy_id": 12, "setup_id": 9, "symbol": "ETH",
        "setup_type": "dca", "dca_frequency": "daily", "is_live": False,
        "mode": mode,
        "budget": {},
    }])
    monkeypatch.setattr(paper_worker, "_get_live_price", lambda *_: 100)
    monkeypatch.setattr(paper_worker, "_get_strategy_setup_payload", lambda *_, **__: {
        **strategy, "setup_type": "dca", "symbol": "ETH",
    })
    monkeypatch.setattr(paper_worker, "_get_current_benchmark_weights", lambda *_: (weights, "analysis"))
    monkeypatch.setattr(paper_worker, "_get_saved_setup_conditions", lambda *_: setup)
    monkeypatch.setattr(paper_worker, "_get_saved_strategy_plan", lambda *_: None)
    monkeypatch.setattr(paper_worker, "get_bot_portfolio_state", lambda *_: {
        "cash": 1000, "qty": 0, "invested": 0,
    })
    monkeypatch.setattr(paper_worker, "get_today_spent_eur", lambda *_: 0)
    monkeypatch.setattr(paper_worker, "_clear_existing_pending_orders_for_day", lambda **_: None)
    monkeypatch.setattr(paper_worker, "_touch_bot_last_run", lambda **_: None)
    order = {"symbol": "ETH", "side": "buy", "quote_amount_eur": 150,
             "estimated_price": 100, "estimated_qty": 1.5}
    monkeypatch.setattr(paper_worker, "build_order_proposal", lambda **kwargs: order if kwargs["decision"]["action"] == "buy" else None)
    saved_orders = []
    auto_calls = []
    monkeypatch.setattr(paper_worker, "_persist_bot_order", lambda **kwargs: saved_orders.append(kwargs) or 14)
    monkeypatch.setattr(paper_worker, "_auto_execute_decision", lambda **kwargs: auto_calls.append(kwargs) or "filled")
    persisted = {}
    monkeypatch.setattr(paper_worker, "_persist_decision_and_order", lambda **kwargs: persisted.update(kwargs) or 13)

    result = paper_worker.run_trading_bot_execution(user_id=7, report_date=date.today())
    assert result["ok"] is True
    assert result["decisions"][0]["action"] == ("hold" if unavailable else "buy")
    assert result["decisions"][0]["decision"]["amount_eur"] == (0 if unavailable else 150)
    assert result["decisions"][0]["execution_status"] == (
        "no_order" if unavailable else "filled" if mode == "auto" else "pending_confirmation"
    )
    assert len(saved_orders) == (0 if unavailable else 1)
    assert len(auto_calls) == (1 if not unavailable and mode == "auto" else 0)
    assert persisted["scores"]["_setup_match"]["status"] == expected_match_status
    assert feed_decisions == ([] if unavailable else [(7, 13)])
