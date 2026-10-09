from backend.ai_agents.trading_bot_agent import _get_saved_strategy_plan


class _Cursor:
    def __init__(self, row):
        self.row = row
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row


def test_bot_reads_confirmed_strategy_and_measured_match_without_ai_snapshot():
    cursor = _Cursor(("76000", ["82000", "86000"], "72000"))
    conn = type("Connection", (), {"cursor": lambda self: cursor})()

    plan = _get_saved_strategy_plan(conn, user_id=7, strategy_id=31, match_score=72)

    assert cursor.params == (31, 7)
    assert "st.user_id = s.user_id" in cursor.query
    assert plan == {
        "entry": 76000.0, "targets": [82000.0, 86000.0],
        "stop_loss": 72000.0, "confidence": 72.0,
        "reason": "saved_strategy_and_measured_setup_match",
    }


def test_bot_does_not_invent_strategy_when_owned_row_is_missing():
    cursor = _Cursor(None)
    conn = type("Connection", (), {"cursor": lambda self: cursor})()
    assert _get_saved_strategy_plan(conn, user_id=7, strategy_id=31, match_score=None) is None


def test_bot_keeps_saved_strategy_but_does_not_invent_match_confidence():
    cursor = _Cursor(("76000", ["82000"], "72000"))
    conn = type("Connection", (), {"cursor": lambda self: cursor})()

    plan = _get_saved_strategy_plan(conn, user_id=7, strategy_id=31, match_score=None)

    assert plan["entry"] == 76000.0
    assert plan["confidence"] is None
    assert plan["reason"] == "saved_strategy_setup_match_unavailable"
