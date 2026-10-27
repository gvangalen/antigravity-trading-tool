import pytest

from backend.engine.trading_bot_execution import execute_manual_decision


class _Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        self.connection.queries.append(sql)
        assert "UPDATE bot_decisions" not in sql

    def fetchone(self):
        return (False, bool(getattr(self.connection, "market_id", None)),
                None, None, None, None, None,
                getattr(self.connection, "market_id", None))


class _Connection:
    def __init__(self):
        self.queries = []

    def cursor(self):
        return _Cursor(self)


def test_paused_bot_cannot_execute_queued_manual_decision():
    connection = _Connection()
    with pytest.raises(RuntimeError, match="paused"):
        execute_manual_decision(conn=connection, user_id=1, bot_id=9, decision_id=42)
    assert any("FOR UPDATE" in sql for sql in connection.queries)


def test_pair_bound_bot_cannot_execute_queued_base_asset_decision():
    connection = _Connection()
    connection.market_id = 73
    with pytest.raises(RuntimeError, match="gekozen handelspaar"):
        execute_manual_decision(conn=connection, user_id=1, bot_id=9, decision_id=42)
    assert not any("UPDATE bot_decisions" in sql for sql in connection.queries)
