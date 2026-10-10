"""One source fixture through score persistence, setup match and paper sizing."""

import json
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.ai_agents import trading_bot_agent as paper_worker
from backend.celery_task import store_daily_scores_task
from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
from backend.domain.setup_market_match import match_setup_from_daily_scores
from backend.engine import bot_brain
from backend.utils import scoring_utils
from backend.utils import macro_interpreter, market_interpreter, technical_interpreter


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
        elif "pg_advisory_xact_lock" in sql or "SELECT 1 FROM bot_decisions" in sql:
            self.rows = []
        else:
            raise AssertionError(f"Unexpected score-chain query: {sql}")

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


@pytest.mark.parametrize("unavailable", [None, "missing", "stale"])
def test_source_to_score2_to_setup_match_to_paper_amount(monkeypatch, unavailable):
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
    assert saved["technical_score"] == (None if unavailable else 60)

    verified = paper_worker._get_daily_scores(store, 7, date.today(), "ETH")
    weights = {key: 1 / 3 for key in ("market_score", "macro_score", "technical_score")}
    setup = {"id": 9, "name": "ETH Smart", "symbol": "ETH", "setup_type": "dca",
             "min_market_score": 70, "min_macro_score": 60, "min_technical_score": 50}
    match = match_setup_from_daily_scores(setup, verified, weights)
    assert match["status"] == ("insufficient_data" if unavailable else "matches")
    if unavailable:
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
    assert decision["action"] == ("hold" if unavailable else "buy")
    assert decision["amount_eur"] == (0 if unavailable else 150)

    # Exercise the worker's actual paper decision path with the same saved
    # score row. No order is created; only the decision payload is inspected.
    monkeypatch.setattr(paper_worker, "get_db_connection", lambda: store)
    monkeypatch.setattr(paper_worker, "_get_active_bots", lambda *_: [{
        "bot_id": 11, "strategy_id": 12, "setup_id": 9, "symbol": "ETH",
        "setup_type": "dca", "dca_frequency": "daily", "is_live": False,
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
    monkeypatch.setattr(paper_worker, "build_order_proposal", lambda **_: None)
    persisted = {}
    monkeypatch.setattr(paper_worker, "_persist_decision_and_order", lambda **kwargs: persisted.update(kwargs) or 13)

    result = paper_worker.run_trading_bot_agent(user_id=7, report_date=date.today())
    assert result["ok"] is True
    assert result["decisions"][0]["action"] == ("hold" if unavailable else "buy")
    assert result["decisions"][0]["decision"]["amount_eur"] == (0 if unavailable else 150)
    assert result["decisions"][0]["execution_status"] == "no_order"
    assert persisted["scores"]["_setup_match"]["status"] == (
        "insufficient_data" if unavailable else "matches"
    )
