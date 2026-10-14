import pytest

from backend.services import bot_live_reconciliation as reconciliation


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        if "from bot_orders" in normalized and "distinct" not in normalized and "for update" not in normalized:
            self.rows = [(
                44, 1, 9, None, "BTC", "buy", "test-exchange",
                "exchange-55", "BTC/EUR", 0.001, 50000,
                self.connection.executed_qty, self.connection.executed_price,
            )] if self.connection.status == "sent" else []
        elif "for update" in normalized:
            self.rows = [(self.connection.status, self.connection.executed_qty, self.connection.executed_price)]
        elif "max(fill_sequence)" in normalized:
            self.rows = [(self.connection.fill_count,)]
        elif "update bot_orders set status" in normalized:
            self.connection.status = params[0]
            self.connection.executed_qty = params[1]
            self.connection.executed_price = params[2]
            self.rows = []
        elif "insert into bot_executions" in normalized:
            self.connection.execution_writes += 1
            self.rows = []
        else:
            self.rows = []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def __init__(self):
        self.status = "sent"
        self.executed_qty = 0
        self.executed_price = None
        self.fill_count = 0
        self.execution_writes = 0
        self.commits = 0

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        pass


def test_reconciliation_records_confirmed_fill_once(monkeypatch):
    connection = _Connection()
    ledger = []
    monkeypatch.setattr(reconciliation, "get_db_connection", lambda: connection)
    monkeypatch.setattr(reconciliation, "_fetch_exchange_order", lambda *_: {
        "status": "closed", "filled": 0.0008, "average": 50100,
    })
    def book(**kwargs):
        ledger.append(kwargs)
        connection.fill_count += 1
    monkeypatch.setattr(reconciliation, "record_bot_ledger_entry", book)

    first = reconciliation.reconcile_live_orders()
    second = reconciliation.reconcile_live_orders()

    assert first == {"processed": 1, "settled": 1, "errors": 0}
    assert second == {"processed": 0, "settled": 0, "errors": 0}
    assert connection.status == "filled"
    assert connection.execution_writes == 1
    assert len(ledger) == 1
    assert ledger[0]["qty_delta"] == 0.0008
    assert ledger[0]["cash_delta_eur"] == -40.08


def test_reconciliation_books_open_partial_fill_once(monkeypatch):
    connection = _Connection()
    ledger = []
    monkeypatch.setattr(reconciliation, "get_db_connection", lambda: connection)
    monkeypatch.setattr(reconciliation, "_fetch_exchange_order", lambda *_: {
        "status": "open", "filled": 0.0008, "average": 50100,
    })
    def book(**kwargs):
        ledger.append(kwargs)
        connection.fill_count += 1
    monkeypatch.setattr(reconciliation, "record_bot_ledger_entry", book)

    assert reconciliation.reconcile_live_orders() == {"processed": 1, "settled": 0, "errors": 0}
    assert reconciliation.reconcile_live_orders() == {"processed": 1, "settled": 0, "errors": 0}
    assert connection.status == "sent"
    assert connection.execution_writes == 1
    assert len(ledger) == 1
    assert ledger[0]["qty_delta"] == 0.0008


def test_reconciliation_books_only_new_quantity_on_terminal_fill(monkeypatch):
    connection = _Connection()
    ledger = []
    exchange = {"status": "open", "filled": 0.0004, "average": 50000}
    monkeypatch.setattr(reconciliation, "get_db_connection", lambda: connection)
    monkeypatch.setattr(reconciliation, "_fetch_exchange_order", lambda *_: exchange.copy())

    def book(**kwargs):
        ledger.append(kwargs)
        connection.fill_count += 1
    monkeypatch.setattr(reconciliation, "record_bot_ledger_entry", book)

    assert reconciliation.reconcile_live_orders()["settled"] == 0
    exchange.update(status="closed", filled=0.001, average=50100)
    assert reconciliation.reconcile_live_orders()["settled"] == 1
    assert [entry["fill_sequence"] for entry in ledger] == [0, 1]
    assert [entry["qty_delta"] for entry in ledger] == pytest.approx([0.0004, 0.0006])
    assert [entry["cash_delta_eur"] for entry in ledger] == [-20, -30.1]
    assert connection.executed_qty == 0.001
    assert connection.status == "filled"


def test_reconciliation_does_not_invent_fill_price_from_limit(monkeypatch):
    connection = _Connection()
    ledger = []
    monkeypatch.setattr(reconciliation, "get_db_connection", lambda: connection)
    monkeypatch.setattr(reconciliation, "_fetch_exchange_order", lambda *_: {
        "status": "closed", "filled": 0.0008, "price": 50000,
    })
    monkeypatch.setattr(reconciliation, "record_bot_ledger_entry", lambda **kwargs: ledger.append(kwargs))

    assert reconciliation.reconcile_live_orders() == {"processed": 1, "settled": 0, "errors": 1}
    assert connection.status == "sent"
    assert ledger == []


def test_reconciliation_rejects_fill_larger_than_submitted_order(monkeypatch):
    connection = _Connection()
    ledger = []
    monkeypatch.setattr(reconciliation, "get_db_connection", lambda: connection)
    monkeypatch.setattr(reconciliation, "_fetch_exchange_order", lambda *_: {
        "status": "closed", "filled": 0.002, "average": 50000,
    })
    monkeypatch.setattr(reconciliation, "record_bot_ledger_entry", lambda **kwargs: ledger.append(kwargs))

    assert reconciliation.reconcile_live_orders() == {"processed": 1, "settled": 0, "errors": 1}
    assert connection.status == "sent"
    assert ledger == []
