"""A queued or direct bot run must stop after its owner was disabled."""

from datetime import date

import pytest

from backend.engine import trading_bot_execution as worker


class OwnerConnection:
    def __init__(self, active: bool):
        self.active = active
        self.queries = []
        self.closed = False

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, parameters):
        self.queries.append((query, parameters))
        assert "FROM users" in query and "is_active=TRUE FOR SHARE" in query
        assert parameters == (7,)

    def fetchone(self):
        return (7,) if self.active else None

    def close(self):
        self.closed = True


@pytest.mark.parametrize("paper_only", [False, True])
def test_disabled_owner_cannot_reach_bot_selection(monkeypatch, paper_only):
    connection = OwnerConnection(active=False)
    monkeypatch.setattr(worker, "get_db_connection", lambda: connection)
    monkeypatch.setattr(worker, "_get_active_bots", lambda *_: pytest.fail("bot selected"))

    result = worker.run_trading_bot_execution(
        user_id=7, report_date=date(2026, 11, 22), paper_only=paper_only,
    )

    assert result == ({"ok": False, "error": "paper_mode_changed"} if paper_only else {
        "ok": True, "date": "2026-11-22", "bots": 0, "decisions": [], "bot_ids": [],
    })
    assert connection.closed
    assert len(connection.queries) == 1


def test_disabled_owner_cannot_claim_manual_decision(monkeypatch):
    connection = OwnerConnection(active=False)
    monkeypatch.setattr(worker, "_claim_bot_decision_for_execution",
                        lambda **_: pytest.fail("decision claimed"))
    with pytest.raises(worker.BotSafetyBlock, match="niet actief"):
        worker.execute_manual_decision(
            conn=connection, user_id=7, bot_id=11, decision_id=13,
        )
    assert len(connection.queries) == 1


def test_enabled_owner_passes_locked_preflight():
    connection = OwnerConnection(active=True)
    assert worker._lock_active_owner(connection, 7)
    assert len(connection.queries) == 1
