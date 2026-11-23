from __future__ import annotations

import asyncio
import os
import inspect
import subprocess
from pathlib import Path

import pytest

from backend.scripts import probe_protected_aapl_bot_crud as bot
from backend.scripts import probe_protected_aapl_stale_quote_read as quote
from backend.scripts import probe_protected_score2_stale_paper as fixture


ROOT = Path(__file__).resolve().parents[4]
DISPATCH = ROOT / "ops/qa/run_finn_production_qa.sh"
WORKFLOW = ROOT / ".github/workflows/finn-production-qa.yml"


def test_bot_proposal_requires_exact_inactive_owner_safe_fields():
    safe = {"name": "QA Bot", "strategy_id": 17, "mode": "manual",
            "is_live": False, "is_active": True, "symbol": "AAPL",
            "budget_total_eur": 10, "paper_initial_cash_eur": 0}
    assert bot._safe_bot_fields(safe, strategy_id=17, bot_name="QA Bot")
    for change in ({"strategy_id": 18}, {"name": "Other"}, {"mode": "auto"},
                   {"is_live": True}, {"is_active": False},
                   {"symbol": "BTC"}, {"budget_total_eur": 11},
                   {"paper_initial_cash_eur": 1}):
        assert not bot._safe_bot_fields(
            {**safe, **change}, strategy_id=17, bot_name="QA Bot",
        )


def test_proposal_diagnostic_allowlists_only_typed_fields():
    projection = {
        "final_operation_id": "create_bot", "final_mode": "CLARIFICATION",
        "terminal_response_type": "response", "missing_inputs": ["budget_total_eur", "secret"],
        "action_draft": {"operation_id": "create_bot", "next_missing_input": "budget_total_eur"},
        "dispatch_count": 1, "attempt_count": 1,
        "response": {"content": "private answer"},
    }
    result = bot._proposal_diagnostic("clarification_required", None, projection)
    assert result == {
        "status": "clarification_required", "error_category": "none",
        "answer_mode": "CLARIFICATION", "response_type": "response",
        "operation": "create_bot", "guided_operation": "create_bot",
        "missing_inputs": ["budget_total_eur"], "requested_slot": "budget_total_eur",
        "dispatch_count": 1, "attempt_count": 1,
    }
    assert "private answer" not in str(result)
    assert "secret" not in str(result)


def test_proposal_diagnostic_unknown_values_do_not_escape():
    result = bot._proposal_diagnostic(
        "private status", "private error",
        {"final_mode": "private mode", "terminal_response_type": "private type",
         "final_operation_id": "private operation", "missing_inputs": ["private slot"],
         "action_draft": {"operation_id": "private guided", "next_missing_input": "private slot"},
         "dispatch_count": 999, "attempt_count": 999},
    )
    assert result == {
        "status": "other", "error_category": "other", "answer_mode": "other",
        "response_type": "other", "operation": "other", "guided_operation": "other",
        "missing_inputs": [], "requested_slot": "other",
        "dispatch_count": "other", "attempt_count": "other",
    }
    assert "private" not in str(result)


def test_proposal_diagnostic_rejects_unexpected_json_shapes():
    result = bot._proposal_diagnostic(
        {"status": "private"}, {"error": "private"},
        {"final_mode": {"mode": "private"}, "missing_inputs": [{"slot": "private"}],
         "action_draft": {"next_missing_input": ["private"]},
         "dispatch_count": True, "attempt_count": [1]},
    )
    assert result["status"] == "other"
    assert result["error_category"] == "other"
    assert result["answer_mode"] == "other"
    assert result["missing_inputs"] == []
    assert result["requested_slot"] == "other"
    assert result["dispatch_count"] == "other"
    assert result["attempt_count"] == "other"
    assert "private" not in str(result)


def test_proposal_diagnostic_reads_are_owner_and_run_scoped():
    source = inspect.getsource(bot._proposal)
    assert "FROM finn_v2_runtime_contracts\n            WHERE run_id=:run_id AND user_id=:user_id" in source
    assert "FROM finn_v2_tool_calls WHERE run_id=:run_id AND user_id=:user_id" in source


@pytest.mark.parametrize("rows,expected", [
    ([], "not_requested"),
    ([("read_linked_strategy", "completed", True)], "available"),
    ([("read_linked_strategies", "failed", False)], "failed"),
    ([("read_linked_strategy", "requested", None)], "requested_not_completed"),
    ([("read_linked_strategy", "completed", True), ("read_linked_strategy", "failed", False)], "available"),
])
def test_strategy_read_status_is_allowlisted(rows, expected):
    assert bot._strategy_read_status(rows) == expected


def test_profile_guards_require_exact_flags_and_bound_owner(monkeypatch):
    namespace = "qa-123456-1-aaaaaaaa-bbbbbbbb"
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_AAPL_BOT_CRUD", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert bot._bound_owner(namespace) == 42
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    with pytest.raises(RuntimeError, match="aapl_bot_not_authorized"):
        bot._bound_owner(namespace)
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="aapl_bot_not_authorized"):
        bot._bound_owner("ordinary-user")

    monkeypatch.setenv("FINN_QA_ALLOW_AAPL_STALE_QUOTE_READ", "1")
    with pytest.raises(RuntimeError, match="aapl_quote_read_not_authorized"):
        quote._bound_owner()
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "0")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    assert quote._bound_owner() == 42
    assert quote._contract_cases()


def test_proposal_only_guard_forbids_execution_and_crud_flag(monkeypatch):
    namespace = "qa-123456-1-aaaaaaaa-bbbbbbbb"
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_AAPL_BOT_PROPOSAL_ONLY", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    assert bot._bound_owner(namespace, proposal_only=True) == 42
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="aapl_bot_not_authorized"):
        bot._bound_owner(namespace, proposal_only=True)
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    monkeypatch.delenv("FINN_QA_ALLOW_AAPL_BOT_PROPOSAL_ONLY")
    monkeypatch.setenv("FINN_QA_ALLOW_AAPL_BOT_CRUD", "1")
    with pytest.raises(RuntimeError, match="aapl_bot_not_authorized"):
        bot._bound_owner(namespace, proposal_only=True)


def test_proposal_only_captures_diagnosis_and_never_confirms(monkeypatch):
    namespace = "qa-123456-1-aaaaaaaa-bbbbbbbb"
    monkeypatch.setattr(bot, "_seed", lambda *_: (42, 17))
    monkeypatch.setattr(bot, "_snapshot", lambda *_: {"bot_configs": 0, "exchange_keys": 0,
                                                     **{table: 0 for table in bot.TRADE_TABLES}})

    async def proposal(*_):
        return {"status": "completed", "proposal_id": "internal-id",
                "confirmation_required": True, "diagnostic": {"status": "completed"}}

    async def forbidden(*_):
        raise AssertionError("confirmation must not run")

    cleaned = []
    monkeypatch.setattr(bot, "_proposal", proposal)
    monkeypatch.setattr(bot, "_confirm_execute", forbidden)
    monkeypatch.setattr(bot, "_cleanup", lambda *args, **kwargs: cleaned.append(args))
    trace = {"stage": "seed", "fixture_state": "not_created"}
    result = asyncio.run(bot._case(namespace, 1, trace, proposal_only=True))
    assert result == {"result": "PASS", "diagnostic_captured": True,
                      "proposal_confirmable": True, "confirmation_attempted": False,
                      "no_bot_or_order": True}
    assert trace["fixture_state"] == "cleaned"
    assert len(cleaned) == 1


class _FakeCursor:
    def __init__(self, *, owner_active=False, trade_rows=0, bots=(),
                 owner_namespace="qa-123456-1-aaaaaaaa-bbbbbbbb", role="user"):
        self.owner_active = owner_active
        self.trade_rows = trade_rows
        self.bots = bots
        self.owner_namespace = owner_namespace
        self.role = role
        self.sql = []
        self.last = ""
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=()):
        self.last = " ".join(sql.split())
        self.sql.append(self.last)

    def fetchone(self):
        if self.last.startswith("SELECT role,is_active,ai_preferences"):
            return (self.role, self.owner_active,
                    {"qa_fixture": bot.MARKER,
                     "qa_namespace": self.owner_namespace})
        if self.last.startswith("SELECT is_active,ai_preferences"):
            return (self.owner_active,
                    {"qa_fixture": bot.MARKER,
                     "qa_namespace": self.owner_namespace})
        if "COUNT(*) FROM exchange_keys" in self.last:
            return (0,)
        if "COUNT(*) FROM" in self.last:
            return (self.trade_rows,)
        if self.last.startswith("SELECT to_regclass"):
            return (None,)
        return None

    def fetchall(self):
        if "FROM bot_configs" in self.last:
            return list(self.bots)
        if "FROM setups" in self.last:
            return [("QA AAPL Setup qa-123456-1-aaaaaaaa-bbbbbbbb", "AAPL")]
        if "FROM strategies" in self.last:
            return [(17, "QA AAPL Strategy qa-123456-1-aaaaaaaa-bbbbbbbb", "AAPL")]
        return []


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


@pytest.mark.parametrize("active,trade_rows,bots", [
    (True, 0, ()),
    (False, 1, ()),
    (False, 0, ((5, 17, "QA AAPL Bot qa-123456-1-aaaaaaaa-bbbbbbbb",
                 "AAPL", "auto", False, 0),)),
])
def test_cleanup_fail_closed_without_deleting_unexpected_child(
        monkeypatch, active, trade_rows, bots):
    cursor = _FakeCursor(owner_active=active, trade_rows=trade_rows, bots=bots)
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(fixture, "_connection", lambda: connection)
    with pytest.raises(RuntimeError, match="aapl_bot_cleanup_failed"):
        bot._cleanup("qa-123456-1-aaaaaaaa-bbbbbbbb", 42, strategy_id=17)
    assert connection.rolled_back
    assert not any(sql.startswith("DELETE FROM") for sql in cursor.sql)
    if active:
        assert not any(sql.startswith("UPDATE bot_configs") for sql in cursor.sql)
    else:
        assert "UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s" in cursor.sql


def test_cleanup_allows_zero_bot_but_only_exact_inactive_child(monkeypatch):
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(fixture, "_connection", lambda: connection)
    bot._cleanup("qa-123456-1-aaaaaaaa-bbbbbbbb", 42, strategy_id=17)
    assert connection.committed
    assert "DELETE FROM users WHERE id=%s" in cursor.sql


@pytest.mark.parametrize("owner_namespace,role", [
    ("qa-123456-1-aaaaaaaa-cccccccc", "user"),
    ("qa-123456-1-aaaaaaaa-bbbbbbbb", "admin"),
])
def test_snapshot_rechecks_exact_child_under_lock_before_action(
        monkeypatch, owner_namespace, role):
    cursor = _FakeCursor(owner_namespace=owner_namespace, role=role)
    monkeypatch.setattr(fixture, "_connection", lambda: _FakeConnection(cursor))
    with pytest.raises(RuntimeError, match="aapl_bot_owner_unsafe"):
        bot._snapshot(42, "qa-123456-1-aaaaaaaa-bbbbbbbb")
    assert cursor.sql == [
        "SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE"
    ]


@pytest.mark.parametrize("profile,actions,execution,accepted", [
    ("aapl_stale_quote_read", "false", "false", True),
    ("aapl_stale_quote_read", "true", "false", False),
    ("aapl_paper_bot_crud", "true", "true", True),
    ("aapl_paper_bot_crud", "true", "false", False),
    ("aapl_bot_proposal_diagnose", "true", "false", True),
    ("aapl_bot_proposal_diagnose", "true", "true", False),
])
def test_dispatch_profiles_use_exact_permissions(tmp_path, profile, actions, execution, accepted):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$QA_DISPATCH_CAPTURE"\n')
    gh.chmod(0o700)
    capture = tmp_path / "capture"
    result = subprocess.run(
        ["bash", str(DISPATCH), "a" * 40, profile, "none", "qa-safe"],
        env=dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
                 QA_DISPATCH_CAPTURE=str(capture),
                 FINN_QA_ALLOW_FIXTURE_ACTIONS=actions,
                 FINN_QA_ALLOW_FIXTURE_EXECUTION=execution),
        capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) is accepted
    assert capture.exists() is accepted


def test_workflow_scopes_bot_flag_and_does_not_expose_financial_actions():
    source = WORKFLOW.read_text()
    script = source.split('cat > "$state_dir/run.sh" <<RUNNER', 1)[1].split("RUNNER", 1)[0]
    assert script.count("export FINN_V2_EXECUTE_BOT_CHANGES=true") == 2
    assert "if [ $(printf '%q' \"$qa_profile\") = aapl_paper_bot_crud ]; then" in script
    assert "FINN_V2_LIVE_TRADING_ENABLED" not in script
    assert "FINN_V2_ACTIVATE_LIVE" not in script
    assert "FINN_QA_ALLOW_AAPL_BOT_CRUD" in source
    assert "FINN_QA_ALLOW_AAPL_STALE_QUOTE_READ" in source
    assert "FINN_QA_ALLOW_AAPL_BOT_PROPOSAL_ONLY" in source
    assert 'if [ $(printf \'%q\' "$qa_profile") = aapl_paper_bot_crud ]; then' in script
    assert 'if [ $(printf \'%q\' "$qa_profile") = aapl_bot_proposal_diagnose ]; then\n            export FINN_V2_EXECUTE_BOT_CHANGES=false' in script
