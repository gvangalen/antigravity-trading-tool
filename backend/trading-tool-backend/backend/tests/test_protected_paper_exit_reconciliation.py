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
                                    "live_calls": 0}
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
                                    "failed_checks": ["cashflow_reconciles"]}
    assert steps == ["quarantine"]


def test_probe_error_category_sanitizes_unexpected_errors():
    assert profile_error_category(
        "trader_paper_exit_reconciliation", RuntimeError("private account 123")
    ) == "paper_exit_probe_runtime_error"
