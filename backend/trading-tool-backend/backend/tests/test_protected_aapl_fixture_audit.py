from __future__ import annotations

from pathlib import Path

import pytest

from backend.scripts import probe_protected_aapl_fixture_audit as probe
from backend.scripts.run_finn_production_qa import ALLOWED_PROFILES, profile_error_category


class FakeConnection:
    def __init__(self, *, statuses=("failed", "failed", "failed"), orders=0):
        self.statuses = statuses
        self.orders = orders
        self.rows = []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def close(self):
        pass

    def execute(self, query, _args):
        if "SELECT id,is_active,is_live,symbol FROM bot_configs" in query:
            self.rows = [(77, False, False, "AAPL")]
        elif "SELECT COUNT(*)" in query:
            table = query.split("FROM ", 1)[1].split()[0]
            count = 1 if table in {"setups", "strategies", "daily_reports", "bot_decisions"} else 0
            self.rows = [(self.orders if table == "bot_orders" else count,)]
        elif "SELECT symbol FROM" in query:
            self.rows = [("AAPL",)]
        elif "SELECT bot_id,status,action" in query:
            self.rows = [(77, "planned", "hold")]
        elif "SELECT status,error_code,conversation_id" in query:
            self.rows = [(status, "responses_tool_round_limit", "first" if index != 1 else "repeat")
                         for index, status in enumerate(self.statuses)]
        elif "SELECT id FROM bot_configs" in query:
            self.rows = [(77,)]
        else:
            raise AssertionError(query)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0]


def test_aapl_audit_reports_only_typed_terminal_state(monkeypatch):
    monkeypatch.setattr(probe, "_scope", lambda _label: (12, False, "qa-synthetic"))
    monkeypatch.setattr(probe.fixture, "_connection", lambda: FakeConnection())

    result = probe.audit(probe.LABEL)

    assert result["fixture_state"] == "QUARANTINED_INACTIVE"
    assert result["safe_to_cleanup"] is True
    assert result["followup_same_conversation"] is True
    assert result["turns"] == [
        {"status": "failed", "error_code": "responses_tool_round_limit"},
    ] * 3
    assert result["trade_rows_present"] is False
    assert "qa-synthetic" not in str(result)


def test_aapl_audit_blocks_nonterminal_child(monkeypatch):
    monkeypatch.setattr(probe, "_scope", lambda _label: (12, False, "qa-synthetic"))
    monkeypatch.setattr(probe.fixture, "_connection", lambda: FakeConnection(
        statuses=("failed", "running", "failed"),
    ))

    result = probe.audit(probe.LABEL)

    assert result["fixture_state"] == "UNSAFE_OR_AMBIGUOUS"
    assert result["safe_to_cleanup"] is False
    assert result["turns"][1] == {"status": "nonterminal_or_other", "error_code": "responses_tool_round_limit"}


def test_aapl_audit_blocks_retained_order(monkeypatch):
    monkeypatch.setattr(probe, "_scope", lambda _label: (12, False, "qa-synthetic"))
    monkeypatch.setattr(probe.fixture, "_connection", lambda: FakeConnection(orders=1))
    result = probe.audit(probe.LABEL)
    assert result["safe_to_cleanup"] is False
    assert result["trade_rows_present"] is True


def test_aapl_scope_rejects_any_other_run_before_read(monkeypatch):
    monkeypatch.setattr(probe, "_verify_prior_report", lambda *_: pytest.fail("prior report read"))
    with pytest.raises(RuntimeError, match="aapl_fixture_audit_label_invalid"):
        probe._scope("audit-45033782173-1-775c4259")


def test_aapl_cleanup_requires_safe_audit_and_checks_postcondition(monkeypatch):
    states = iter([
        {"fixture_state": "QUARANTINED_INACTIVE", "safe_to_cleanup": True},
        {"fixture_state": "NO_RETAINED_FIXTURE", "safe_to_cleanup": False},
    ])
    monkeypatch.setattr(probe, "audit", lambda _label: next(states))
    monkeypatch.setattr(probe, "_scope", lambda _label: (12, False, "qa-synthetic"))
    monkeypatch.setattr(probe.fixture, "_connection", lambda: FakeConnection())
    calls = []
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args, **kwargs: calls.append((args, kwargs)))

    assert probe.cleanup(probe.LABEL) == {"fixture_state": "CLEANED", "cleanup_verified": True}
    assert calls == [(("qa-synthetic", 12, 77), {
        "require_safe_pair_cleanup": True,
        "allow_planned_decisions": True,
        "require_aapl_quote_fixture": True,
    })]


def test_aapl_cleanup_rejects_unsafe_state(monkeypatch):
    monkeypatch.setattr(probe, "audit", lambda _label: {
        "fixture_state": "UNSAFE_OR_AMBIGUOUS", "safe_to_cleanup": False,
    })
    with pytest.raises(RuntimeError, match="aapl_fixture_cleanup_unsafe"):
        probe.cleanup(probe.LABEL)


def test_aapl_profiles_are_exactly_guarded_in_both_dispatch_paths():
    root = Path(__file__).resolve().parents[4]
    workflow = (root / ".github/workflows/finn-production-qa.yml").read_text()
    shell = (root / "ops/qa/run_finn_production_qa.sh").read_text()
    for source in (workflow, shell):
        assert "aapl_paper_quote_fixture_audit" in source
        assert "aapl_paper_quote_fixture_cleanup" in source
        assert probe.LABEL in source
    assert {"aapl_paper_quote_fixture_audit", "aapl_paper_quote_fixture_cleanup"} <= ALLOWED_PROFILES
    assert profile_error_category("aapl_paper_quote_fixture_cleanup", RuntimeError(
        "aapl_fixture_cleanup_unsafe",
    )) == "aapl_fixture_cleanup_unsafe"
