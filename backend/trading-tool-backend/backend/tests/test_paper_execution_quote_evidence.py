"""The saved Paper fill price and dated conversion must share one quote."""

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from backend.engine import trading_bot_execution as worker
from backend.services.portfolio_fx_service import trade_quote_context


def _quote():
    now = datetime.now(timezone.utc)
    return trade_quote_context(
        price=347.14, price_at=now - timedelta(minutes=5),
        row_quote="USDT", catalog_quote="USDT", usd_fx=None,
        quote_fx={"eur_per_unit": 0.84, "observed_at": now - timedelta(minutes=10)},
        require_usd=False, now=now,
    )


class _OrderCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=()):
        self.connection.statements.append((sql, params))
        self.row = None
        if "FROM bot_configs" in sql:
            self.row = ("auto", False, True, 100, 1000, 200, 1, 200, None)
        elif "SELECT cash_eur FROM bot_portfolios" in sql:
            self.row = (1000,)
        elif "UPDATE bot_decisions" in sql and "scores_json" in sql:
            self.row = (3,)
        elif "UPDATE bot_orders" in sql and "RETURNING id" in sql:
            self.row = (4,)
        elif not any(marker in sql for marker in (
            "UPDATE bot_executions", "UPDATE bot_decisions",
        )):
            raise AssertionError(sql)

    def fetchone(self):
        return self.row


class _OrderConnection:
    def __init__(self):
        self.statements = []

    def cursor(self):
        return _OrderCursor(self)


def test_auto_paper_buy_saves_the_exact_execution_quote(monkeypatch):
    quote = _quote()
    connection = _OrderConnection()
    quote_reads = []
    ledger = []
    monkeypatch.setattr(worker, "_recheck_paper_trade_entry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "_get_trade_quote_fx_context",
                        lambda *_args, **_kwargs: quote_reads.append(1) or quote)
    monkeypatch.setattr(worker, "_claim_bot_decision_for_execution", lambda **_kwargs: True)
    monkeypatch.setattr(worker, "_recheck_auto_buy_limits", lambda **_kwargs: None)
    monkeypatch.setattr(worker, "_require_current_setup_revision_for_buy", lambda **_kwargs: None)
    monkeypatch.setattr(worker, "record_bot_ledger_entry", lambda **kwargs: ledger.append(kwargs))

    result = worker._auto_execute_decision(
        conn=connection, user_id=1, bot_id=2, decision_id=3,
        order={"symbol": "BTC", "side": "buy", "estimated_qty": 1,
               "estimated_price": 100, "quote_amount_eur": 100},
        is_live=False, mode="auto",
    )

    assert result == "filled"
    assert len(quote_reads) == 1
    evidence = next(json.loads(params[0]) for sql, params in connection.statements
                    if "UPDATE bot_decisions" in sql and "scores_json" in sql)
    filled = next(params for sql, params in connection.statements
                  if "UPDATE bot_orders" in sql and "RETURNING id" in sql)
    assert filled[0] == evidence["execution_eur_price"] == quote["market_price_eur"]
    assert filled[0] == evidence["execution_source_price"] * evidence["execution_fx_eur_per_unit"]
    assert ledger[0]["price_eur"] == filled[0]
    assert evidence["execution_source_price_at"] == quote["market_price_at"].isoformat()


class _SqliteCursor:
    def __init__(self, connection):
        self.cursor = connection.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.cursor.close()

    def execute(self, sql, params=()):
        return self.cursor.execute(sql, params)


class _SqliteConnection:
    def __init__(self):
        self.connection = sqlite3.connect(":memory:")

    def cursor(self):
        return _SqliteCursor(self.connection)


def test_failed_paper_buy_rolls_back_quote_and_ledger_writes():
    connection = _SqliteConnection()
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE effects (kind TEXT)")
        cursor.execute("INSERT INTO effects VALUES ('planned_order')")

    def fail_after_evidence():
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO effects VALUES ('quote_evidence')")
            cursor.execute("INSERT INTO effects VALUES ('cash_ledger')")
        raise RuntimeError("later execution failure")

    with pytest.raises(RuntimeError, match="later execution failure"):
        worker._run_paper_auto_buy_atomically(connection, fail_after_evidence)

    with connection.cursor() as cursor:
        assert cursor.execute("SELECT kind FROM effects").fetchall() == [("planned_order",)]
