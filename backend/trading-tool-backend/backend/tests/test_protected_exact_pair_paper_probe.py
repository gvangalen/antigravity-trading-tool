"""Contract checks for the protected exact-pair Paper result verifier."""

import math

import pytest

from backend.scripts import probe_protected_score2_exact_pair_paper as probe


class _Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.current = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params):
        if "FROM daily_scores" in sql:
            self.current = "scores"
        elif "FROM bot_decisions" in sql:
            self.current = "decision"
        elif "FROM bot_orders" in sql:
            self.current = "orders"
        elif "FROM bot_ledger" in sql:
            self.current = "ledger"
        elif "FROM bot_portfolios" in sql:
            self.current = "portfolio"
        elif "FROM exchange_keys" in sql:
            self.current = "keys"
        else:
            raise AssertionError("unexpected verifier query")

    def fetchone(self):
        return self.rows[self.current]

    def fetchall(self):
        return self.rows[self.current]


class _Connection:
    def __init__(self, rows):
        self.rows = rows

    def cursor(self):
        return _Cursor(self.rows)

    def close(self):
        pass


def _rows(*, market_id=7, execution_price=23050):
    approved = 50.0
    qty = math.floor(approved / execution_price * 100_000_000) / 100_000_000
    spent = round(qty * execution_price, 2)
    return {
        "scores": (40, 80, 60),
        "decision": ("buy", approved, 7, {"setup_match": {"status": "matches"}}, "executed"),
        "orders": [("filled", "paper", market_id, execution_price, qty, spent)],
        "ledger": [(7, -spent, qty)],
        "portfolio": (100 - spent, qty, False, True),
        "keys": (0,),
    }


def test_paper_verifier_accepts_repriced_exact_pair_fill(monkeypatch):
    """A fresh execution quote may differ from the earlier preflight quote."""
    monkeypatch.setattr(probe.fixture, "_connection", lambda: _Connection(_rows()))

    result = probe._verify(1, 2, "2026-10-28", 7, "USDT", 23000)

    assert result["result"] == "PASS"
    assert result["pair"] == "ETH/USDT"
    assert result["environment"] == "paper"


def test_paper_verifier_identifies_wrong_market_id(monkeypatch):
    monkeypatch.setattr(probe.fixture, "_connection", lambda: _Connection(_rows(market_id=8)))

    with pytest.raises(RuntimeError, match="exact_pair_paper_order_market_mismatch"):
        probe._verify(1, 2, "2026-10-28", 7, "USDT", 23000)


def test_paper_verifier_marks_large_price_move_inconclusive(monkeypatch):
    monkeypatch.setattr(probe.fixture, "_connection", lambda: _Connection(_rows(execution_price=25000)))

    with pytest.raises(RuntimeError, match="exact_pair_probe_price_window_unstable"):
        probe._verify(1, 2, "2026-10-28", 7, "USDT", 23000)
