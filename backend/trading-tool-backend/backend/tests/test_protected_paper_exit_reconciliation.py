"""No database calls: test the protected Paper-exit collector boundary."""

import pytest

from backend.scripts import probe_protected_paper_exit_reconciliation as probe
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-ad9fe0d3-deadbeef"


def test_probe_requires_authorization_before_source_read(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", raising=False)
    monkeypatch.setattr(probe, "_preflight", lambda: pytest.fail("unexpected source read"))
    with pytest.raises(RuntimeError, match="^paper_exit_fixture_not_authorized$"):
        probe.run(NAMESPACE)


def test_probe_replays_once_and_cleans_only_after_contract_pass(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_preflight", lambda: (2, {"market_price": 100,
                                                        "market_price_eur": 90}))
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_trade", lambda *args: steps.append("seed_trade"))
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            return None
        def fetchone(self):
            return (910, 0.001)
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(trading_bot_execution, "run_trading_bot_execution",
                        lambda *args, **kwargs: (steps.append("run") or {"ok": True}))
    monkeypatch.setattr(probe, "_evidence", lambda *args: {"fixture": "private"})
    monkeypatch.setattr(probe, "check_paper_exit",
                        lambda evidence: {"result": "PASS", "failed_checks": []})
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "PASS", "failed_checks": [],
                                    "exit_decisions": 1, "replay_duplicate_sells": 0,
                                    "engine_calls": 2, "live_calls": 0,
                                    "rendered_ui_checked": False,
                                    "gate_status": "PARTIAL"}
    assert steps == ["seed_trade", "run", "run", "cleanup"]


def test_probe_quarantines_when_persisted_effect_does_not_reconcile(monkeypatch):
    from backend.engine import trading_bot_execution

    monkeypatch.setenv("FINN_QA_ALLOW_PAPER_EXIT_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_preflight", lambda: (2, {}))
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_trade", lambda *args: None)
    class Cursor:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            return None
        def fetchone(self):
            return (910, 0.001)
    class Connection:
        def cursor(self):
            return Cursor()
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    monkeypatch.setattr(trading_bot_execution, "run_trading_bot_execution",
                        lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(probe, "_evidence", lambda *args: {})
    monkeypatch.setattr(probe, "check_paper_exit",
                        lambda evidence: {"result": "FAIL",
                                          "failed_checks": ["cashflow_reconciles"]})
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "FAIL",
                                    "failed_checks": ["cashflow_reconciles"],
                                    "rendered_ui_checked": False,
                                    "gate_status": "FAIL", "engine_calls": 2,
                                    "live_calls": 0}
    assert steps == ["quarantine"]


def test_probe_error_category_sanitizes_unexpected_errors():
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError("private account 123")
    ) == "paper_exit_probe_runtime_error"


@pytest.mark.parametrize("failed_statement,phase", [
    (2, "setup_update"), (3, "strategy_update"), (4, "bot_update"),
    (5, "portfolio_update"), (6, "decision_insert"),
    (7, "order_insert"), (8, "ledger_insert"),
])
def test_opening_fixture_reports_fixed_statement_phase(monkeypatch, failed_statement, phase):
    class Cursor:
        index = -1
        rowcount = 1
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            return None
        def execute(self, *_args):
            self.index += 1
            if self.index == failed_statement:
                raise TypeError("private SQL value")
        def fetchone(self):
            return (5,)
    class Connection:
        def __init__(self):
            self.cursor_value = Cursor()
            self.rolled_back = False
        def cursor(self):
            return self.cursor_value
        def rollback(self):
            self.rolled_back = True
        def close(self):
            return None
    conn = Connection()
    monkeypatch.setattr(probe.fixture, "_connection", lambda: conn)
    with pytest.raises(RuntimeError, match=f"^paper_exit_open_{phase}_failed$"):
        probe._seed_trade(11, 22, 33, {"market_price": 100, "market_price_eur": 90})
    assert conn.rolled_back
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError(f"paper_exit_open_{phase}_failed")
    ) == f"paper_exit_open_{phase}_failed"


def test_live_exchange_guard_blocks_attempt_and_restores_entrypoint():
    from backend.engine import trading_bot_execution

    original = trading_bot_execution._execute_on_exchange_sync
    with probe._guard_live_exchange() as attempts:
        with pytest.raises(RuntimeError, match="^paper_exit_live_execution_attempt$"):
            trading_bot_execution._execute_on_exchange_sync(None, 1, "exchange", "BTC", "sell", 1, 1)
    assert len(attempts) == 1
    assert trading_bot_execution._execute_on_exchange_sync is original


def test_persisted_evidence_uses_execution_quote_not_earlier_decision_quote(monkeypatch):
    raw = {
        "source_price": 95, "fx_eur_per_unit": 0.88,
        "source_price_at": "2026-11-08T09:00:00+00:00",
        "execution_source_price": 100, "execution_fx_eur_per_unit": 0.9,
        "execution_source_price_currency": "USDT",
        "execution_source_price_at": "2026-11-08T09:12:00+00:00",
        "execution_fx_observed_at": "2026-11-08T09:10:00+00:00",
        "execution_eur_price": 90, "execution_qty": 0.5,
        "execution_proceeds_eur": 45,
    }
    rows = [(51, raw, "executed", "sell", "filled", "paper", 0.5, 90, 45, 91)]
    projection = {
        "execution_source_price_currency": "USDT",
        "execution_source_price_at": raw["execution_source_price_at"],
        "execution_fx_observed_at": raw["execution_fx_observed_at"],
        "execution_qty": 0.5, "execution_eur_price": 90,
        "execution_proceeds_eur": 45,
    }
    async def history(_user_id):
        return [{"decision_id": 51, "exit_evidence": projection}]
    monkeypatch.setattr(probe, "_history", history)
    fetched = {
        0: rows, 1: (55, 0), 2: [(45, -0.5, 90, 91)], 3: (1,),
        4: (False, {"qa_fixture": probe.fixture.FIXTURE_MARKER,
                    "qa_namespace": NAMESPACE}),
        5: (0,), 6: (False,), 7: (0,),
    }
    class Cursor:
        index = -1
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
        def execute(self, *args):
            self.index += 1
        def fetchone(self):
            return fetched[self.index]
        def fetchall(self):
            return fetched[self.index]
    class Connection:
        cursor_instance = Cursor()
        def cursor(self):
            return self.cursor_instance
        def close(self):
            return None
    monkeypatch.setattr(probe.fixture, "_connection", Connection)
    evidence = probe._evidence(NAMESPACE, 11, 22, 2, 10, 0.5, 0)
    assert evidence["execution_source_price"] == 100
    assert "source_price" not in evidence
    assert probe.check_paper_exit(evidence)["result"] == "PASS"
