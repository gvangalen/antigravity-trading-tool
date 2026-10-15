import pytest

from backend.scripts import recover_uncertain_bot_order as recovery


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        self.connection.statements.append((normalized, params))
        if "from bot_orders" in normalized and "for update" not in normalized:
            self.row = (1, 44, 9, 12, "BTC", "buy", 0.001,
                        "test-exchange", None, self.connection.status)
        elif "from bot_orders" in normalized and "for update" in normalized:
            self.row = (self.connection.status, None, "test-exchange", "BTC", "buy", 0.001, 12)
        elif "update bot_orders set status='rejected'" in normalized:
            self.connection.status = "rejected"
            self.row = None
        elif "update bot_orders set exchange_order_id" in normalized:
            self.connection.status = "sent"
            self.row = None
        else:
            self.row = None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.status = "unknown_exchange_state"
        self.statements = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        return _Cursor(self)

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


def test_uncertain_order_stays_blocked_without_explicit_exchange_review(monkeypatch):
    monkeypatch.setattr(recovery, "get_db_connection", lambda: pytest.fail("must not open DB"))
    with pytest.raises(ValueError, match="Confirm no order"):
        recovery.recover_order(
            user_id=1, order_id=44, action="verified_no_order", exchange_order_id=None,
            operator_id="operator", evidence_reference="incident-123", confirmation="",
        )


def test_verified_no_order_clears_block_and_records_audit(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(recovery, "get_db_connection", lambda: conn)

    result = recovery.recover_order(
        user_id=1, order_id=44, action="verified_no_order", exchange_order_id=None,
        operator_id="operator", evidence_reference="incident-123",
        confirmation="I VERIFIED NO EXCHANGE ORDER",
    )

    assert result == {"order_id": 44, "action": "verified_no_order", "status": "rejected"}
    assert conn.status == "rejected"
    assert conn.commits == 1 and conn.closed
    assert any("insert into bot_order_recovery_events" in sql for sql, _ in conn.statements)
    assert any("pg_advisory_xact_lock" in sql for sql, _ in conn.statements)


def test_attached_exchange_order_reconciles_after_audited_update(monkeypatch):
    conn = _Connection()
    monkeypatch.setattr(recovery, "get_db_connection", lambda: conn)
    monkeypatch.setattr(recovery, "_fetch_verified_exchange_order", lambda *_: {
        "id": "exchange-55", "symbol": "BTC/EUR", "side": "buy", "amount": 0.001,
    })
    calls = []
    monkeypatch.setattr(recovery, "reconcile_live_orders", lambda **kwargs: calls.append(kwargs) or {"settled": 1})

    result = recovery.recover_order(
        user_id=1, order_id=44, action="attach_exchange_order",
        exchange_order_id="exchange-55", operator_id="operator",
        evidence_reference="incident-123", confirmation="I VERIFIED THIS EXCHANGE ORDER",
    )

    assert conn.status == "sent" and conn.commits == 1
    assert calls == [{"user_id": 1, "order_id": 44}]
    assert result["reconciliation"] == {"settled": 1}
    assert any("insert into bot_order_recovery_events" in sql for sql, _ in conn.statements)
