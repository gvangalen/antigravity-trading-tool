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
