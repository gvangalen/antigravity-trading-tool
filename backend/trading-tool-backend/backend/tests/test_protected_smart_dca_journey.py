from __future__ import annotations

import inspect
import os
import subprocess
from pathlib import Path

import pytest

from backend.scripts import probe_protected_smart_dca_journey as probe

ROOT = Path(__file__).resolve().parents[4]
DISPATCH = ROOT / "ops/qa/run_finn_production_qa.sh"
WORKFLOW = ROOT / ".github/workflows/finn-production-qa.yml"
NAMESPACE = "qa-123456-1-aaaaaaaa-bbbbbbbb"


def test_exact_owner_and_permission_guard(monkeypatch):
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv(probe.FLAG, "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    assert probe._bound_owner(NAMESPACE) == 42
    for key in (probe.FLAG, "FINN_QA_ALLOW_FIXTURE_ACTIONS",
                "FINN_QA_ALLOW_FIXTURE_EXECUTION"):
        monkeypatch.setenv(key, "0")
        with pytest.raises(RuntimeError, match="smart_dca_journey_not_authorized"):
            probe._bound_owner(NAMESPACE)
        monkeypatch.setenv(key, "1")
    with pytest.raises(RuntimeError, match="smart_dca_journey_not_authorized"):
        probe._bound_owner("ordinary-user")


def test_setup_must_be_complete_score_trigger_without_buy_day():
    name = probe._names(NAMESPACE)[0]
    correct = {
        "name": name, "symbol": "BTC", "quote_currency": "USDT",
        "timeframe": "1D", "setup_type": "dca", "dca_trigger_mode": "benchmark",
        "dca_frequency": "weekly", "dca_amount_mode": "score_bands",
        "score_source": "benchmark_score",
        "low_threshold": 26, "high_threshold": 76,
        "low_score_percent": 150, "mid_score_percent": 100,
        "high_score_percent": 50, "base_amount": 200, "dca_day": None,
    }
    assert probe._safe_setup(correct, name)
    for key, value in (("quote_currency", "EUR"), ("score_source", "market_score"),
                       ("dca_trigger_mode", "calendar"),
                       ("dca_day", "friday"), ("low_threshold", 45),
                       ("high_score_percent", 100), ("name", "other")):
        bad = {**correct, key: value}
        assert not probe._safe_setup(bad, name)


def test_bot_proposal_rejects_wrong_parent_live_or_cash():
    name = probe._names(NAMESPACE)[1]
    correct = {"strategy_id": 11, "name": name, "symbol": "BTC",
               "mode": "manual", "is_live": False, "is_active": True,
               "budget_total_eur": 200, "paper_initial_cash_eur": 0}
    assert probe._safe_bot(correct, 11, name)
    for key, value in (("strategy_id", 12), ("symbol", "AAPL"),
                       ("mode", "automatic"), ("is_live", True),
                       ("is_active", False), ("paper_initial_cash_eur", 200),
                       ("budget_total_eur", 100), ("name", "other")):
        assert not probe._safe_bot({**correct, key: value}, 11, name)


@pytest.mark.parametrize("bad", ["score_source", "fourth_point", "strategy_pair",
                                  "bot_pair", "market_asset", "bot_inactive"])
def test_saved_contract_rejects_wrong_curve_or_pair(monkeypatch, bad):
    name, bot_name = probe._names(NAMESPACE)
    curve = probe._expected_curve(name)
    if bad == "score_source":
        curve = {**curve, "input": "market_score"}
    if bad == "fourth_point":
        curve = {**curve, "points": [*curve["points"][:3], {"x": 100, "y": 1.0}]}
    setup = (11, name, "BTC", "1D", "dca", "benchmark", "weekly",
             None, 0, 100, 77, "AAPL" if bad == "market_asset" else "BTC", "USDT")
    strategy = (12, 11, f"{name} Strategy", "BTC", "custom", 200, curve,
                78 if bad == "strategy_pair" else 77,
                {"dca_amount_semantics": "planned_exact"})
    bot = (13, 12, bot_name, "BTC", "manual", False,
           bad != "bot_inactive", 0, 200, 78 if bad == "bot_pair" else 77)

    class Cursor:
        last = ""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql, _params):
            self.last = sql

        def fetchall(self):
            if "FROM setups s" in self.last:
                return [setup]
            if "FROM strategies" in self.last:
                return [strategy]
            if "FROM bot_configs" in self.last:
                return [bot]
            raise AssertionError(self.last)

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(probe.fixture, "_connection", lambda: Connection())
    monkeypatch.setattr(probe, "_snapshot", lambda *_: {
        **{table: 0 for table in (*probe.TRADE_TABLES, "bot_portfolios", "exchange_keys")},
        "setups": 1, "strategies": 1, "bot_configs": 1,
    })
    with pytest.raises(RuntimeError, match="smart_dca_journey_fixture_unsafe"):
        probe._saved(42, NAMESPACE)


def test_cleanup_stops_before_delete_and_quarantines_on_unexpected_child(monkeypatch):
    class Cursor:
        last = ""
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, sql, _params):
            self.last = sql
            assert not sql.lstrip().startswith("DELETE")
        def fetchone(self):
            return ("user", False, {"qa_fixture": probe.MARKER,
                                    "qa_namespace": NAMESPACE})

    class Connection:
        def __init__(self):
            self.rolled_back = False
        def cursor(self):
            return Cursor()
        def rollback(self):
            self.rolled_back = True
        def close(self):
            pass

    connection = Connection()
    calls = []
    monkeypatch.setattr(probe.fixture, "_connection", lambda: connection)
    def reject_saved(_user_id, _namespace, *, connection, locked):
        calls.append((connection, locked))
        raise RuntimeError("unexpected child row")
    monkeypatch.setattr(probe, "_saved", reject_saved)
    monkeypatch.setattr(probe, "_quarantine", lambda *_: calls.append("quarantined"))
    with pytest.raises(RuntimeError, match="smart_dca_journey_cleanup_failed"):
        probe._cleanup(NAMESPACE, 42)
    assert connection.rolled_back
    assert calls == [(connection, True), "quarantined"]


def test_cleanup_reports_unverified_quarantine(monkeypatch):
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *_):
            return False
        def execute(self, *_):
            pass
        def fetchone(self):
            return ("user", False, {"qa_fixture": probe.MARKER,
                                    "qa_namespace": NAMESPACE})

    class Connection:
        def cursor(self):
            return Cursor()
        def rollback(self):
            pass
        def close(self):
            pass

    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(probe, "_saved",
                        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("changed")))
    monkeypatch.setattr(probe, "_quarantine",
                        lambda *_args: (_ for _ in ()).throw(RuntimeError("quarantine failed")))
    with pytest.raises(RuntimeError, match="smart_dca_journey_quarantine_unverified"):
        probe._cleanup(NAMESPACE, 42)


@pytest.mark.parametrize("actions,execution,accepted", [
    ("true", "true", True), ("true", "false", False), ("false", "true", False),
])
def test_dispatch_permission_pair(tmp_path, actions, execution, accepted):
    gh = tmp_path / "gh"
    gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$QA_DISPATCH_CAPTURE"\n')
    gh.chmod(0o700)
    capture = tmp_path / "capture"
    result = subprocess.run(
        ["bash", str(DISPATCH), "a" * 40, "smart_dca_journey", "none", "qa-safe"],
        env=dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
                 QA_DISPATCH_CAPTURE=str(capture),
                 FINN_QA_ALLOW_FIXTURE_ACTIONS=actions,
                 FINN_QA_ALLOW_FIXTURE_EXECUTION=execution),
        capture_output=True, text=True, check=False,
    )
    assert (result.returncode == 0) is accepted
    assert capture.exists() is accepted


def test_workflow_scopes_nonfinancial_profile():
    source = WORKFLOW.read_text()
    script = source.split('cat > "$state_dir/run.sh" <<RUNNER', 1)[1].split("RUNNER", 1)[0]
    assert source.count("export FINN_QA_ALLOW_SMART_DCA_JOURNEY=1") == 1
    assert 'if [ $(printf \'%q\' "$qa_profile") = smart_dca_journey ]; then' in script
    assert "FINN_V2_LIVE_TRADING_ENABLED" not in script
    assert "FINN_V2_ACTIVATE_LIVE" not in script
    assert 'os.getenv(FLAG) != "1"' in inspect.getsource(probe._bound_owner)
    assert "WHERE run_id=:run_id AND user_id=:user_id" in inspect.getsource(probe._turn)
    assert "run_trading_bot_execution" not in inspect.getsource(probe)
    assert "_persist_bot_order" not in inspect.getsource(probe)
