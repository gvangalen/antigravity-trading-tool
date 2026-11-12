import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_manual_trade_temporary_matrix as temporary
from backend.scripts import run_finn_production_qa as qa


async def _noop(*_args, **_kwargs):
    return None


def _args(tmp_path):
    return SimpleNamespace(
        fixture_namespace="qa-123-1-aabbccdd-eeff0011",
        release_sha="a" * 40, manifest_id="manual-trade-test",
        manifest_bundle_path=None, manifest_root=str(tmp_path),
        manifest_private_key_path=str(tmp_path / "key"),
        manifest_crypto_script=None, report_path=str(tmp_path / "report.json"),
        checkout=str(tmp_path), base_url="https://example.test",
        release_marker=str(tmp_path / "marker"), run_label="manual-trade-test",
        workflow_run_id="123-1", runner_revision=None,
    )


def test_temporary_email_is_accepted_by_auth_response_schema():
    from backend.schemas.auth_schema import UserOut

    namespace = "qa-123-1-aabbccdd-eeff0011"
    email = temporary._email(namespace)
    response = UserOut(id=42, email=email, role="user", is_active=True,
                       first_name="FINN QA temporary", last_name=None,
                       ai_plan=None, ai_requests_limit_day=None,
                       ai_requests_used_day=None)
    assert response.email == email


def _prepare(monkeypatch, tmp_path):
    args = _args(tmp_path)
    (tmp_path / "manifest.json").write_text("{}")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.setenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    monkeypatch.setattr(qa, "manifest_path", lambda **_kwargs: tmp_path / "manifest.json")
    monkeypatch.setattr(qa, "sha256_file", lambda _path: "b" * 64)
    monkeypatch.setattr(qa, "load_manifest", lambda **_kwargs: [{
        "case_id": "manual-1", "message": "Maak een handmatig voorstel",
        "expected_operation_id": "create_manual_trade_plan",
        "fixture_action": "read_only"}])
    monkeypatch.setattr(temporary, "_source_preflight", _noop)
    monkeypatch.setattr(temporary, "_create_child", lambda *_args: _pair())
    monkeypatch.setattr(temporary, "_seed_btc_choices", _noop)
    monkeypatch.setattr(temporary, "prepare_fixture", _noop)
    monkeypatch.setattr(temporary, "_extend_lease", _noop)
    monkeypatch.setattr(temporary, "_child_quiescent", lambda *_args: _truth())
    monkeypatch.setattr(temporary, "_parent_unchanged", lambda *_args: _truth())
    monkeypatch.setattr(temporary, "_find_child", lambda *_args: _child())
    monkeypatch.setattr(temporary, "_revoke_child", _noop)
    monkeypatch.setattr(temporary, "_delete_child", _noop)
    original_fstat = temporary.os.fstat
    monkeypatch.setattr(temporary.os, "fstat", lambda fd: object() if fd == 9 else original_fstat(fd))
    return args


async def _pair():
    return 42, "parent-hash"


async def _truth():
    return True


async def _child():
    return 42


def test_successful_matrix_revokes_before_exact_cleanup(monkeypatch, tmp_path):
    args = _prepare(monkeypatch, tmp_path)
    events = []

    async def revoke(*_args):
        events.append("revoke")

    async def delete(*_args):
        events.append("delete")

    monkeypatch.setattr(temporary, "_revoke_child", revoke)
    monkeypatch.setattr(temporary, "_delete_child", delete)
    monkeypatch.setattr(qa, "request_json", lambda **_kwargs: (
        (200 if "revoke" not in events else 401), {}, 0.01, None))

    class Process:
        pid = 1234

        def wait(self, timeout):
            assert timeout == 2400
            child_report = Path(args.report_path).with_suffix(".child-report.json")
            child_report.write_text(json.dumps({
                "outcome": "passed", "qa_status": "COMPLETED",
                "cases": [{"case_id": "manual-1", "case_status": "completed"}],
                "planned_count": 1, "attempted_count": 1,
                "completed_count": 1, "failed_count": 0,
                "not_run_count": 0, "incomplete": False}))
            return 0

    def start_child(command, **kwargs):
        environment = kwargs["env"]
        assert environment["FINN_QA_USER_ID"] == "42"
        assert environment["FINN_QA_TEMP_CHILD_RUN"] == "1"
        assert environment["FINN_QA_FIXTURE_NAMESPACE"] == args.fixture_namespace
        assert command[command.index("--fixture-namespace") + 1] == args.fixture_namespace
        assert kwargs["pass_fds"] == (9,)
        return Process()

    monkeypatch.setattr(temporary.subprocess, "Popen", start_child)
    report = {}
    assert temporary.run(args, report)["cleanup_verified"] is True
    assert events == ["revoke", "delete"]
    assert report["temporary_qa_child_deleted"] is True
    assert report["temporary_qa_parent_unchanged"] is True
    assert __import__("os").environ["FINN_QA_USER_ID"] == "7"


def test_failed_matrix_quarantines_child_without_deleting_evidence(monkeypatch, tmp_path):
    args = _prepare(monkeypatch, tmp_path)
    events = []

    async def revoke(*_args):
        events.append("revoke")

    async def delete(*_args):
        events.append("delete")

    monkeypatch.setattr(temporary, "_revoke_child", revoke)
    monkeypatch.setattr(temporary, "_delete_child", delete)

    class Process:
        def wait(self, timeout):
            return 1

    monkeypatch.setattr(temporary.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    report = {}
    with pytest.raises(RuntimeError, match="matrix_failed"):
        temporary.run(args, report)
    assert events == ["revoke"]
    assert report["temporary_qa_child_quarantined"] is True
    assert report.get("temporary_qa_child_deleted") is not True


def test_parent_change_records_quarantine_before_failing(monkeypatch, tmp_path):
    args = _prepare(monkeypatch, tmp_path)

    async def changed(*_args):
        return False

    monkeypatch.setattr(temporary, "_parent_unchanged", changed)

    class Process:
        def wait(self, timeout):
            return 1

    monkeypatch.setattr(temporary.subprocess, "Popen", lambda *_args, **_kwargs: Process())
    report = {}
    with pytest.raises(RuntimeError, match="temporary_qa_parent_changed"):
        temporary.run(args, report)
    journal = json.loads(Path(args.report_path).with_suffix(".temp-journal.json").read_text())
    assert journal["phase"] == "quarantined"
    assert report["temporary_qa_parent_unchanged"] is False
    assert report["temporary_qa_child_quarantined"] is True
    assert report["temporary_qa_token_revoked"] is True


def test_interrupted_matrix_does_not_replay_and_revokes(monkeypatch, tmp_path):
    args = _prepare(monkeypatch, tmp_path)
    journal = Path(args.report_path).with_suffix(".temp-journal.json")
    temporary._journal(journal, {"kind": temporary.FINN_TEMP_QA_KIND,
                                 "namespace": args.fixture_namespace,
                                 "release_sha": args.release_sha,
                                 "parent": 7, "phase": "matrix_running"})
    events = []

    async def revoke(*_args):
        events.append("revoke")

    monkeypatch.setattr(temporary, "_revoke_child", revoke)
    monkeypatch.setattr(temporary.subprocess, "Popen", lambda *_args, **_kwargs:
                        pytest.fail("interrupted matrix was replayed"))
    report = {}
    with pytest.raises(RuntimeError, match="prior_attempt_interrupted"):
        temporary.run(args, report)
    assert events == ["revoke"]
    assert report["temporary_qa_child_quarantined"] is True


def test_manifest_cannot_authorize_other_operation():
    with pytest.raises(RuntimeError, match="operation_invalid"):
        temporary._assert_manual_trade_manifest([{
            "expected_operation_id": "create_bot", "fixture_action": "safe_execution"}])


def test_temporary_database_phases_share_one_event_loop():
    import asyncio

    async def loop_identity():
        return id(asyncio.get_running_loop())

    assert temporary._db(loop_identity()) == temporary._db(loop_identity())


@pytest.mark.parametrize("legacy_parent_change", [False, True])
def test_quarantined_diagnosis_reads_only_bound_prior_checkpoint(monkeypatch, tmp_path, legacy_parent_change):
    import asyncio
    import os
    from contextlib import asynccontextmanager

    namespace = "qa-123-1-aabbccdd-eeff0011"
    old_dir = tmp_path / "finn-production-qa-123-1"
    old_dir.mkdir()
    old_dir.chmod(0o700)
    journal = old_dir / "finn-production-qa-123-1.temp-journal.json"
    journal.write_text(json.dumps({"kind": temporary.FINN_TEMP_QA_KIND,
                                   "namespace": namespace, "parent": 7,
                                   "release_sha": "aabbccdd" + "a" * 32,
                                   "phase": "matrix_complete" if legacy_parent_change else "quarantined"}))
    journal.chmod(0o600)
    prior_report = old_dir / "finn-production-qa-123-1.json"
    if legacy_parent_change:
        prior_report.write_text(json.dumps({
            "workflow_run_id": "123-1", "target_sha": "aabbccdd" + "a" * 32,
            "temporary_qa_failure_phase": "matrix_complete",
            "temporary_qa_parent_unchanged": False,
            "temporary_qa_child_present": True,
            "temporary_qa_child_quarantined": True,
            "temporary_qa_token_revoked": True,
        }))
        prior_report.chmod(0o600)
    child_report = old_dir / "finn-production-qa-123-1.child-report.json"
    child_report.write_text(json.dumps({"workflow_run_id": "123-1",
                                        "target_sha": "aabbccdd" + "a" * 32,
                                        "outcome": "failed", "qa_status": "INCOMPLETE",
                                        "error_category": "privateToken123", "planned_count": 6,
                                        "attempted_count": 2, "completed_count": 1,
                                        "failed_count": 1, "not_run_count": 4,
                                        "auth_preflight": {"http_status": 200,
                                                           "fixture_authenticated": True},
                                        "failure_summary": {"product": 1,
                                                            "runner": 0,
                                                            "infrastructure": 0},
                                        "cases": [{"case_status": "completed",
                                                   "run_id": "finn-v2-run-" + "a" * 32,
                                                   "terminal": {"response": {"mode": "READ"}},
                                                   "failure_classification": "product",
                                                   "error_category": "privateToken123",
                                                   "polling_sse_equal": False,
                                                   "fixture_action": {
                                                       "outcome": "proposal_evidence_failed",
                                                       "error_category": "manual_trade_proposal_invalid",
                                                       "manual_trade_proposal_evidence": {
                                                           "passed": False,
                                                           "private_data": "private prompt"},
                                                       "manual_trade_saved_evidence": {
                                                           "plan": {"passed": False}},
                                                       "manual_trade_replay_unchanged": False},
                                                   "message": "private prompt"}]}))
    child_report.chmod(0o600)
    monkeypatch.setattr(temporary, "QA_STATE_ROOT", tmp_path)
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    monkeypatch.delenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", raising=False)
    monkeypatch.delenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", raising=False)
    original_fstat = temporary.os.fstat
    monkeypatch.setattr(temporary.os, "fstat", lambda fd: object() if fd == 9 else original_fstat(fd))

    class Session:
        async def execute(self, query, params):
            if "exchange_keys" in str(query):
                return _DbResult({"keys": 0, "orders": 0, "bots": 0,
                                  "strategies": 0, "executable_plans": 0})
            owner = params["owner"]
            return _DbResult({"role": "user", "is_active": owner == 7,
                              "ai_preferences": ({"qa_fixture": temporary.PARENT_MARKER}
                                                 if owner == 7 else
                                                 {"qa_fixture": temporary.FINN_TEMP_QA_KIND,
                                                  "finn_temp_qa": {"namespace": namespace,
                                                                   "parent": 7,
                                                                   "status": "revoked"}})})

        async def rollback(self):
            pass

    @asynccontextmanager
    async def session_factory():
        yield Session()

    async def find_child(*_args):
        return 42

    async def quiescent(*_args):
        return True

    monkeypatch.setattr(temporary, "async_session_factory", session_factory)
    monkeypatch.setattr(temporary, "_find_child", find_child)
    monkeypatch.setattr(temporary, "_child_quiescent", quiescent)
    monkeypatch.setattr(temporary, "_db", lambda awaitable: asyncio.run(awaitable))
    monkeypatch.setattr(qa, "manual_trade_wait_evidence", lambda run_id, *, owner_id: (
        {"typed_wait": True, "reason_class": "manual_trade_benchmark_unavailable"}
        if run_id == "finn-v2-run-" + "a" * 32 and owner_id == 42 else {}))
    result = temporary.diagnose_quarantined(f"diagnose-{namespace}")
    assert result["child_revoked"] and result["child_quiescent"]
    assert result["parent_marker_valid"] and not result["unsafe_child_rows_present"]
    assert result["prior_target_sha"] == "aabbccdd" + "a" * 32
    assert result.get("prior_parent_changed") is (True if legacy_parent_change else None)
    assert result["original_child_report_summary"]["attempted_count"] == 2
    projected = result["original_child_report_summary"]["case_statuses"][0]
    assert projected["case_status"] == "completed"
    assert projected["failure_classification"] == "product"
    assert projected["manual_trade_proposal_passed"] is False
    assert projected["manual_trade_saved_plan_passed"] is False
    assert projected["manual_trade_replay_unchanged"] is False
    assert projected["polling_sse_equal"] is False
    assert projected["fixture_action_error_category"] == "manual_trade_proposal_invalid"
    assert projected["unexpected_manual_trade_wait_typed"] is True
    assert projected["unexpected_manual_trade_wait_reason_class"] == "manual_trade_benchmark_unavailable"
    assert "private prompt" not in json.dumps(result)
    assert "privateToken123" not in json.dumps(result)
    assert result["original_child_report_summary"]["error_category"] is None
    assert child_report.exists() and journal.exists()
    if legacy_parent_change:
        previous = json.loads(prior_report.read_text())
        prior_report.write_text(json.dumps({**previous, "temporary_qa_parent_unchanged": True}))
        with pytest.raises(RuntimeError, match="diagnose_journal_binding_changed"):
            temporary.diagnose_quarantined(f"diagnose-{namespace}")
        prior_report.write_text(json.dumps(previous))
    with child_report.open("wb") as handle:
        handle.truncate(8 * 1024 * 1024 + 1)
    with pytest.raises(RuntimeError, match="diagnose_report_invalid"):
        temporary.diagnose_quarantined(f"diagnose-{namespace}")


def test_temporary_workflow_never_restarts_one_shot_profiles():
    workflow = (Path(__file__).resolve().parents[4] / ".github" / "workflows"
                / "finn-production-qa.yml").read_text()
    guard = 'if [[ "$QA_PROFILE" =~ ^manual_trade_temporary_(matrix|cleanup|diagnose)$ ]]; then'
    assert workflow.count(guard) == 2
    assert workflow.index(guard) < workflow.index('if [ "$incomplete" = "true" ]')
    assert 'manual_trade_temporary_diagnose' in workflow


class _DbResult:
    def __init__(self, value):
        self.value = value

    def mappings(self):
        return self

    def one_or_none(self):
        return self.value

    def one(self):
        return self.value

    def all(self):
        return self.value

    def scalar_one(self):
        return self.value


class _CleanupSession:
    def __init__(self, *, unknown_loose=False, noncascade=False, late_row=False):
        self.rows = {"setups": 2, "market_data_indicators": 1}
        if unknown_loose:
            self.rows["mystery_evidence"] = 1
        self.noncascade = noncascade
        self.late_row = late_row
        self.user_exists = True
        self.committed = False
        self.rolled_back = False
        self.snapshot = dict(self.rows)
        self.owner_columns = [
            {"schema_name": "public", "table_name": table, "column_name": "user_id"}
            for table in self.rows]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, _exc, _tb):
        if exc_type:
            self.rolled_back = True
            self.rows = dict(self.snapshot)
            self.user_exists = True

    async def execute(self, query, _params=None):
        sql = str(query)
        if "SELECT role,is_active,ai_preferences FROM users" in sql:
            return _DbResult({"role": "user", "is_active": False,
                              "ai_preferences": {"qa_fixture": temporary.FINN_TEMP_QA_KIND,
                                                 "finn_temp_qa": {"namespace": "qa-123-1-aabbccdd-eeff0011",
                                                                  "status": "revoked"}}})
        if "SELECT\n              (SELECT count(*) FROM exchange_keys" in sql:
            return _DbResult({"keys": 0, "orders": 0, "bots": 0,
                              "strategies": 0, "executable_plans": 0})
        if "FROM pg_constraint c" in sql:
            return _DbResult([{"schema_name": "public", "table_name": "setups",
                               "column_name": "user_id", "delete_action": (
                                   "a" if self.noncascade else "c"), "key_columns": 1}])
        if "FROM pg_class t" in sql:
            return _DbResult(self.owner_columns)
        if "DELETE FROM users" in sql:
            self.user_exists = False
            self.rows["setups"] = 0
            if self.late_row:
                self.rows["setups"] = 1
            return SimpleNamespace(rowcount=1)
        if "DELETE FROM" in sql:
            for table in self.rows:
                if f'"{table}"' in sql:
                    self.rows[table] = 0
            return SimpleNamespace(rowcount=1)
        if "SELECT count(*) FROM" in sql:
            for table, count in self.rows.items():
                if f'"{table}"' in sql:
                    return _DbResult(count)
        raise AssertionError(sql)

    async def commit(self):
        self.committed = True


def test_cleanup_deletes_known_loose_owner_rows_and_verifies_absence(monkeypatch):
    import asyncio
    session = _CleanupSession()
    monkeypatch.setattr(temporary, "async_session_factory", lambda: session)
    asyncio.run(temporary._delete_child(42, "qa-123-1-aabbccdd-eeff0011"))
    assert session.committed
    assert not session.user_exists
    assert session.rows == {"setups": 0, "market_data_indicators": 0}


def test_cleanup_deletes_child_rows_with_legacy_non_cascade_fk(monkeypatch):
    import asyncio
    session = _CleanupSession(noncascade=True)
    monkeypatch.setattr(temporary, "async_session_factory", lambda: session)
    asyncio.run(temporary._delete_child(42, "qa-123-1-aabbccdd-eeff0011"))
    assert session.committed
    assert session.rows == {"setups": 0, "market_data_indicators": 0}


@pytest.mark.parametrize("failure", ["unknown_loose", "late_row"])
def test_cleanup_rolls_back_on_schema_drift_or_remaining_row(monkeypatch, failure):
    import asyncio
    session = _CleanupSession(**{failure: True})
    monkeypatch.setattr(temporary, "async_session_factory", lambda: session)
    with pytest.raises(RuntimeError):
        asyncio.run(temporary._delete_child(42, "qa-123-1-aabbccdd-eeff0011"))
    assert session.rolled_back
    assert session.user_exists
    assert not session.committed


def test_inherited_lock_remains_held_by_child_after_parent_close(tmp_path):
    import fcntl
    import os
    import subprocess
    import sys

    lock_file = tmp_path / "qa.lock"
    parent_fd = os.open(lock_file, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(parent_fd, fcntl.LOCK_EX)
        child = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(0.35)"],
            pass_fds=(parent_fd,), stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        os.close(parent_fd)
        parent_fd = -1
        challenger = os.open(lock_file, os.O_RDWR)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(challenger, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert child.wait(timeout=3) == 0
            fcntl.flock(challenger, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(challenger)
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
