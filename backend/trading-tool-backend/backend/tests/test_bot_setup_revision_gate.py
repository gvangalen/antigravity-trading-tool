import json
from datetime import date, datetime

import pytest

from backend.ai_agents import trading_bot_agent
from backend.ai_agents.trading_bot_agent import (
    _persist_decision_and_order,
    _require_current_setup_revision_for_buy,
)


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, row):
        self.last_cursor = _Cursor(row)

    def cursor(self):
        return self.last_cursor


def test_old_bot_buy_cannot_execute_after_owner_setup_edit():
    changed = datetime(2026, 10, 11, 10, 5)
    conn = _Connection((9, 10, "2026-10-11T10:00:00", True, 10, 9, changed))

    with pytest.raises(RuntimeError, match="changed since this decision"):
        _require_current_setup_revision_for_buy(
            conn=conn, user_id=7, bot_id=8, decision_id=12,
        )

    assert "FOR SHARE OF b, s, st" in conn.last_cursor.query
    assert conn.last_cursor.params == (12, 7, 8)


def test_legacy_buy_without_recorded_revision_fails_closed():
    conn = _Connection((9, 10, None, False, 10, 9, None))

    with pytest.raises(RuntimeError, match="changed since this decision"):
        _require_current_setup_revision_for_buy(
            conn=conn, user_id=7, bot_id=8, decision_id=12,
        )


def test_matching_owner_setup_revision_allows_new_bot_buy():
    current = datetime(2026, 10, 11, 10, 5)
    conn = _Connection((9, 10, current.isoformat(), True, 10, 9, current))

    _require_current_setup_revision_for_buy(
        conn=conn, user_id=7, bot_id=8, decision_id=12,
    )


def test_worker_rejects_buy_if_setup_changed_after_it_was_read():
    changed = datetime(2026, 10, 11, 10, 5)
    conn = _Connection((changed,))

    with pytest.raises(RuntimeError, match="changed during bot assessment"):
        _persist_decision_and_order(
            conn=conn, user_id=7, bot_id=8, strategy_id=10, setup_id=9,
            report_date=date(2026, 10, 11), decision={"action": "buy", "symbol": "ETH",
                                                    "amount_eur": 100},
            scores={}, setup_revision="2026-10-11T10:00:00",
        )

    assert "FOR SHARE" in conn.last_cursor.query
    assert conn.last_cursor.params == (9, 7)


def test_paper_hold_persists_the_actual_guardrail_reason(monkeypatch):
    conn = _Connection((42,))
    monkeypatch.setattr(trading_bot_agent, "_persist_trade_plan", lambda **kwargs: None)

    decision_id = _persist_decision_and_order(
        conn=conn, user_id=7, bot_id=8, strategy_id=10, setup_id=9,
        report_date=date(2026, 10, 11),
        decision={
            "action": "hold", "symbol": "ETH", "amount_eur": 0,
            "strategy_reason": "Scheduled DCA blocked by guardrails: insufficient_funds",
            "guardrail_reason": "insufficient_funds",
            "guardrails_result": {"allowed": False, "blocked_by": "insufficient_funds"},
        },
        scores={}, setup_revision="2026-10-11T10:00:00",
    )

    assert decision_id == 42
    saved_scores = json.loads(conn.last_cursor.params[-1])
    assert saved_scores["guardrail_reason"] == "insufficient_funds"
    assert saved_scores["guardrails_result"]["blocked_by"] == "insufficient_funds"
    assert saved_scores["strategy_reason"].startswith("Scheduled DCA blocked")


def test_reassessment_cannot_reopen_an_executed_daily_decision(monkeypatch):
    conn = _Connection(None)

    def unexpected_trade_plan(**_kwargs):
        raise AssertionError("an executed decision must not receive a new plan")

    monkeypatch.setattr(trading_bot_agent, "_persist_trade_plan", unexpected_trade_plan)
    decision_id = _persist_decision_and_order(
        conn=conn, user_id=7, bot_id=8, strategy_id=10, setup_id=9,
        report_date=date(2026, 10, 11),
        decision={"action": "hold", "symbol": "ETH", "amount_eur": 0},
        scores={},
    )

    assert decision_id is None
    assert "bot_decisions.status NOT IN ('executed', 'executing')" in conn.last_cursor.query
