"""Secret-free checks for the read-only prior-run fixture audit."""

from contextlib import contextmanager
import json

import pytest

from backend.scripts import probe_protected_trader_fixture_audit as audit
from backend.scripts.probe_protected_paper_exit_reconciliation import _stage
from backend.scripts.run_finn_production_qa import profile_error_category


class Cursor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.rows = None

    def execute(self, _query, _params):
        self.rows = next(self.responses)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


class Connection:
    def __init__(self, responses):
        self.cursor_value = Cursor(responses)
        self.closed = False

    @contextmanager
    def cursor(self):
        yield self.cursor_value

    def close(self):
        self.closed = True


LABEL = "audit-42502525173-1-9a72d5e4"
NAMESPACE = "qa-42502525173-1-9a72d5e4-1234abcd"


def test_audit_does_not_infer_cleanup_from_absent_fixture(monkeypatch):
    conn = Connection([[]])
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    assert audit.run(LABEL) == {
        "fixture_state": "NO_RETAINED_FIXTURE", "cleanup_verified": False,
        "stage": "BEFORE_SEED_OR_CLEANED",
    }
    assert conn.closed


def test_audit_accepts_only_attempted_incomplete_prior_paper_run(monkeypatch):
    conn = Connection([[]])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1",
        "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    assert audit.run(LABEL)["fixture_state"] == "NO_RETAINED_FIXTURE"


def test_audit_reports_only_bounded_quarantine_state(monkeypatch):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)],
        [(0,)], [("assessment", 1)], [(0,)], [(0,)], [(0,)],
    ])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_: None)
    result = audit.run(LABEL)
    assert result == {
        "fixture_state": "QUARANTINED_INACTIVE", "cleanup_verified": False,
        "paper_open_present": True, "paper_exit_decision_present": False,
        "paper_exit_order_present": False, "paper_exit_execution_present": False,
        "paper_exit_ledger_present": False,
    }
    assert "17" not in str(result) and NAMESPACE not in str(result)
    assert conn.closed


def test_pair_audit_requires_matching_prior_pair_run_and_reports_only_fixed_presence(monkeypatch):
    conn = Connection([
        [(17, False, {"qa_namespace": NAMESPACE})], [(False, False)], [(0,)],
        [(3,)], [(2,)], [(2,)], [(2,)], [(0,)], [(0,)],
    ])
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_pair_score_continuity",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    assert audit.run(LABEL, expected_profile="trader_pair_score_continuity") == {
        "fixture_state": "QUARANTINED_INACTIVE", "cleanup_verified": False,
        "pair_configs_present": True, "pair_market_readings_present": True,
        "pair_technical_readings_present": True, "pair_scores_present": True,
        "orders_present": False, "executions_present": False,
    }
    assert conn.closed


def test_pair_audit_rejects_paper_prior_report_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": True, "outcome": "incomplete",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL, expected_profile="trader_pair_score_continuity")


def test_pair_cleanup_requires_inactive_uncredentialed_child_and_verifies_zero_rows(monkeypatch):
    before = Connection([
        [(17, {"qa_namespace": NAMESPACE})], [(22, False, False)],
    ])
    after = Connection([[(0,)], *([[(0,)]] * 9)])
    connections = iter((before, after))
    monkeypatch.setattr(audit, "PAIR_CLEANUP_LABELS", {LABEL})
    monkeypatch.setattr(audit.fixture, "_connection", lambda: next(connections))
    monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
    cleaned = []
    monkeypatch.setattr(audit.fixture, "_cleanup", lambda *args, **kwargs: cleaned.append((args, kwargs)))
    result = audit.cleanup_pair(LABEL)
    assert result == {"fixture_state": "CLEANED", "cleanup_verified": True}
    assert cleaned == [((NAMESPACE, 17, 22), {"require_safe_pair_cleanup": True})]
    assert before.closed and after.closed
    assert NAMESPACE not in str(result) and "17" not in str(result)


def test_pair_cleanup_refuses_active_or_credentialed_child_before_write(monkeypatch):
    for responses, code in (
        ([[(17, {"qa_namespace": "wrong"})]], "trader_pair_cleanup_owner_unsafe"),
        ([[(17, {"qa_namespace": NAMESPACE})], []], "trader_pair_cleanup_bot_unsafe"),
    ):
        monkeypatch.setattr(audit, "PAIR_CLEANUP_LABELS", {LABEL})
        monkeypatch.setattr(audit, "_verify_prior_report", lambda *_args: None)
        monkeypatch.setattr(audit.fixture, "_connection", lambda values=responses: Connection(values))
        monkeypatch.setattr(audit.fixture, "_cleanup", lambda *_args: pytest.fail("unexpected write"))
        with pytest.raises(RuntimeError, match=f"^{code}$"):
            audit.cleanup_pair(LABEL)


def test_pair_cleanup_label_is_bound_to_audited_runs(monkeypatch):
    assert audit.PAIR_CLEANUP_LABELS == {
        "audit-42543306392-1-20322165",
        "audit-42546922438-1-169d0252",
        "audit-42549516935-1-1d8c6a3a",
        "audit-42551140172-1-43009b2a",
    }
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    with pytest.raises(RuntimeError, match="^trader_pair_cleanup_label_not_allowed$"):
        audit.cleanup_pair("audit-42502525173-1-9a72d5e4")


@pytest.mark.parametrize("blocked_table", ["bot_decisions", "bot_orders", "bot_executions", "bot_ledger"])
def test_locked_cleanup_blocks_prior_decisions_and_trades_without_delete(monkeypatch, blocked_table):
    queries = []
    class LockedCursor:
        rowcount = 0
        def execute(self, query, params):
            queries.append(query)
        def fetchone(self):
            if len(queries) == 1:
                return ({"qa_fixture": audit.fixture.FIXTURE_MARKER,
                         "qa_namespace": NAMESPACE},)
            if len(queries) == 2:
                return (False,)
            if len(queries) == 4:
                return (0,)
            if len(queries) in (5, 6, 7, 8):
                return (int(blocked_table in queries[-1]),)
            raise AssertionError("unexpected query")
        def fetchall(self):
            return [(22, False, False)]
    class LockedConnection:
        rolled_back = False
        committed = False
        @contextmanager
        def cursor(self):
            yield LockedCursor()
        def rollback(self):
            self.rolled_back = True
        def commit(self):
            self.committed = True
        def close(self):
            pass
    conn = LockedConnection()
    monkeypatch.setattr(audit.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match="^fixture_cleanup_failed$"):
        audit.fixture._cleanup(NAMESPACE, 17, 22, require_safe_pair_cleanup=True)
    assert conn.rolled_back and not conn.committed
    assert "FOR UPDATE" in queries[0] and "FOR UPDATE" in queries[2]
    assert blocked_table in queries[-1]
    assert not any("DELETE FROM" in query for query in queries)


def test_audit_rejects_unscoped_label_before_database(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_label_invalid"):
        audit.run("audit-not-a-run")


def test_audit_requires_matching_prior_paper_report(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    def unavailable(*_args, **_kwargs):
        raise OSError("private path")
    monkeypatch.setattr(audit.Path, "read_text", unavailable)
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_unavailable"):
        audit.run(LABEL)


def test_audit_rejects_another_prior_profile(monkeypatch):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1", "profile": "auth_preflight",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL)


@pytest.mark.parametrize("attempted,outcome", [(False, "incomplete"), (True, "passed")])
def test_audit_rejects_unattempted_or_successful_prior_run(monkeypatch, attempted, outcome):
    monkeypatch.setattr(audit.fixture, "_connection", lambda: pytest.fail("database touched"))
    monkeypatch.setattr(audit.Path, "read_text", lambda *_a, **_k: json.dumps({
        "workflow_run_id": "42502525173-1",
        "profile": "trader_paper_exit_reconciliation",
        "target_sha": "9a72d5e4c8e10533a6a7359861e242efdd2c4808",
        "protected_profile_attempted": attempted, "outcome": outcome,
    }))
    with pytest.raises(RuntimeError, match="trader_fixture_audit_prior_report_mismatch"):
        audit.run(LABEL)


def test_paper_exit_stage_codes_hide_exception_text():
    with pytest.raises(RuntimeError, match="^paper_exit_paper_open_failed$"):
        with _stage("paper_open"):
            raise TypeError("private fixture data")
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError("paper_exit_paper_open_failed")
    ) == "paper_exit_paper_open_failed"
    assert profile_error_category(
        "trader_paper_exit_fixture_audit", RuntimeError("private fixture data")
    ) == "trader_fixture_audit_runtime_error"
