from __future__ import annotations

import asyncio
import inspect
import os
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from backend.scripts import probe_protected_aapl_closed_market_journey as probe


ROOT = Path(__file__).resolve().parents[4]
DISPATCH = ROOT / "ops/qa/run_finn_production_qa.sh"
WORKFLOW = ROOT / ".github/workflows/finn-production-qa.yml"
NAMESPACE = "qa-123456-1-aaaaaaaa-bbbbbbbb"


def test_guard_requires_exact_profile_flags_and_namespace(monkeypatch):
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_AAPL_CLOSED_JOURNEY", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert probe._bound_owner(NAMESPACE) == 42
    for key, value in (("FINN_QA_ALLOW_AAPL_CLOSED_JOURNEY", "0"),
                       ("FINN_QA_ALLOW_FIXTURE_ACTIONS", "0"),
                       ("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")):
        monkeypatch.setenv(key, value)
        with pytest.raises(RuntimeError, match="aapl_journey_not_authorized"):
            probe._bound_owner(NAMESPACE)
        monkeypatch.setenv(key, "1")
    with pytest.raises(RuntimeError, match="aapl_journey_not_authorized"):
        probe._bound_owner("ordinary-user")


@pytest.mark.parametrize("profile,actions,execution,accepted", [
    ("aapl_closed_market_journey", "true", "true", True),
    ("aapl_closed_market_journey", "true", "false", False),
    ("aapl_closed_market_journey", "false", "true", False),
])
def test_dispatch_requires_both_nonfinancial_fixture_flags(
        tmp_path, profile, actions, execution, accepted):
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


def test_workflow_scopes_only_nonfinancial_flags():
    source = WORKFLOW.read_text()
    script = source.split('cat > "$state_dir/run.sh" <<RUNNER', 1)[1].split("RUNNER", 1)[0]
    assert 'if [ $(printf \'%q\' "$qa_profile") = aapl_closed_market_journey ]; then' in script
    assert source.count("export FINN_QA_ALLOW_AAPL_CLOSED_JOURNEY=1") == 1
    assert script.count("export FINN_V2_EXECUTE_BOT_CHANGES=true") == 2
    assert script.count("export FINN_V2_EXECUTE_SETUP_CHANGES=true") == 2
    assert script.count("export FINN_V2_EXECUTE_STRATEGY_CHANGES=true") == 2
    assert "FINN_V2_LIVE_TRADING_ENABLED" not in script
    assert "FINN_V2_ACTIVATE_LIVE" not in script
    assert "aapl_closed_market_journey" in source


def test_turn_contract_read_is_owner_bound():
    source = inspect.getsource(probe._turn)
    assert "WHERE run_id=:run_id AND user_id=:user_id" in source


def test_objects_stop_on_trade_rows_before_reading_other_rows(monkeypatch):
    counts = {"bot_configs": 0, "bot_portfolios": 0, "exchange_keys": 0,
              **{table: 0 for table in probe.bot.TRADE_TABLES}}
    counts["bot_orders"] = 1
    monkeypatch.setattr(probe.bot, "_snapshot", lambda *_: counts)
    with pytest.raises(RuntimeError, match="aapl_journey_fixture_unsafe"):
        probe._objects(42, NAMESPACE)


class _CleanupCursor:
    def __init__(self, *, unexpected_setup=False):
        self.unexpected_setup = unexpected_setup
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
            return ("user", False, {"qa_fixture": probe.bot.MARKER,
                                    "qa_namespace": NAMESPACE})
        if self.last.startswith("SELECT COUNT(*)"):
            return (0,)
        if self.last.startswith("SELECT to_regclass"):
            return (None,)
        return None

    def fetchall(self):
        if self.last.startswith("SELECT id,name,symbol FROM setups"):
            name = "Unexpected" if self.unexpected_setup else probe.bot._names(NAMESPACE)[0]
            return [(11, name, "AAPL")]
        if self.last.startswith("SELECT id,setup_id,name,symbol FROM strategies"):
            return [(12, 11, probe.bot._names(NAMESPACE)[1], "AAPL")]
        if self.last.startswith("SELECT id,strategy_id,name,symbol,mode"):
            return [(13, 12, probe.bot._names(NAMESPACE)[2], "AAPL", "manual", False, 0, 10)]
        return []


class _CleanupConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


def test_cleanup_rejects_unexpected_child_before_delete(monkeypatch):
    connection = _CleanupConnection(_CleanupCursor(unexpected_setup=True))
    quarantined = []
    monkeypatch.setattr(probe.fixture, "_connection", lambda: connection)
    monkeypatch.setattr(probe.bot, "_quarantine", lambda *args: quarantined.append(args))
    with pytest.raises(RuntimeError, match="aapl_journey_cleanup_failed"):
        probe._cleanup(NAMESPACE, 42)
    assert connection.rolled_back
    assert len(quarantined) == 1
    assert not any(sql.startswith("DELETE FROM") for sql in connection.cursor_instance.sql)
    assert not any(sql.startswith("UPDATE bot_configs") for sql in connection.cursor_instance.sql)


def test_cleanup_accepts_only_exact_expected_child(monkeypatch):
    connection = _CleanupConnection(_CleanupCursor())
    monkeypatch.setattr(probe.fixture, "_connection", lambda: connection)
    probe._cleanup(NAMESPACE, 42)
    assert connection.committed
    assert "UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s" in connection.cursor_instance.sql
    assert "DELETE FROM users WHERE id=%s" in connection.cursor_instance.sql


def test_complete_synthetic_journey_uses_one_conversation_and_cleans(monkeypatch):
    state = {"setup_id": None, "strategy_id": None, "bot_id": None}
    turns = []
    cleaned = []
    monkeypatch.setattr(probe, "_seed", lambda *_: 42)
    monkeypatch.setattr(probe, "_objects", lambda *_: state.copy())
    monkeypatch.setattr(probe.bot, "_snapshot", lambda *_: {
        "bot_configs": int(state["bot_id"] is not None), "bot_portfolios": 0,
        "exchange_keys": 0, **{table: 0 for table in probe.bot.TRADE_TABLES}})
    monkeypatch.setattr(probe.quote, "_source", lambda: {
        "price": Decimal("250.10"), "at": object()})
    monkeypatch.setattr(probe.quote, "_answer_current_price", lambda *_: True)
    monkeypatch.setattr(probe.quote, "_answer_moments", lambda *_: {
        "current_source_time_explained": True})
    monkeypatch.setattr(probe.bot, "_verify", lambda *_: None)
    monkeypatch.setattr(probe, "_cleanup", lambda *args: cleaned.append(args))

    async def turn(_user, message, *, conversation_id=None):
        turns.append((message, conversation_id))
        index = len(turns)
        operations = {2: "create_setup", 3: "create_strategy",
                      4: "create_strategy", 5: "create_bot", 6: "create_bot"}
        operation = operations.get(index)
        return {"status": "completed", "conversation_id": "same-conversation",
                "proposal_id": f"proposal-{index}" if index in {2, 4, 6} else None,
                "confirmation_required": index in {2, 4, 6}, "answer": "dated quote",
                "operation": operation, "guided_operation": operation,
                "supplied_inputs": {"setup_id": 11, "strategy_id": 12},
                "dispatch_count": 1, "attempt_count": 1}

    async def setup_strategy(_user, proposal_id, trace):
        trace["confirmed_count"] = trace.get("confirmed_count", 0) + 1
        trace["executed_count"] = trace.get("executed_count", 0) + 1
        if proposal_id == "proposal-2":
            state["setup_id"] = 11
            return {"conversation_id": "same-conversation",
                    "next_step": {"setup_id": 11}}
        state["strategy_id"] = 12
        return {"conversation_id": "same-conversation",
                "next_step": {"strategy_id": 12}}

    async def confirm_bot(*_):
        state["bot_id"] = 13
        return "succeeded", "already_executed"

    monkeypatch.setattr(probe, "_turn", turn)
    monkeypatch.setattr(probe.journey, "_confirm_and_execute", setup_strategy)
    monkeypatch.setattr(probe.bot, "_confirm_execute", confirm_bot)
    trace = {"stage": "seed", "fixture_state": "not_created"}
    result = asyncio.run(probe._case(NAMESPACE, 1, trace))
    assert result["result"] == "PASS"
    assert len(turns) == 6
    assert turns[0][1] is None
    assert all(conversation == "same-conversation" for _, conversation in turns[1:])
    assert "entry 250 USD, stop-loss 240 USD, target 270 USD" in turns[3][0]
    assert trace["fixture_state"] == "cleaned"
    assert len(cleaned) == 1


def test_incomplete_quote_never_reaches_confirmation_and_still_cleans(monkeypatch):
    cleaned = []
    monkeypatch.setattr(probe, "_seed", lambda *_: 42)
    monkeypatch.setattr(probe, "_objects", lambda *_: {
        "setup_id": None, "strategy_id": None, "bot_id": None})
    monkeypatch.setattr(probe.bot, "_snapshot", lambda *_: {
        "bot_configs": 0, "bot_portfolios": 0, "exchange_keys": 0,
        **{table: 0 for table in probe.bot.TRADE_TABLES}})
    monkeypatch.setattr(probe.quote, "_source", lambda: {
        "price": Decimal("250"), "at": object()})

    async def bad_quote(*_, **__):
        return {"status": "unavailable", "proposal_id": None}

    monkeypatch.setattr(probe, "_turn", bad_quote)
    monkeypatch.setattr(probe, "_cleanup", lambda *args: cleaned.append(args))
    trace = {"stage": "seed", "fixture_state": "not_created"}
    with pytest.raises(RuntimeError, match="aapl_journey_quote_missing"):
        asyncio.run(probe._case(NAMESPACE, 1, trace))
    assert trace["fixture_state"] == "cleaned"
    assert len(cleaned) == 1
