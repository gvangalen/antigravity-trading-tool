"""No database or network access: prove protected probe control flow."""

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from backend.scripts import probe_protected_btc_pair_score_continuity as probe
from backend.scripts.run_finn_production_qa import profile_error_category


NAMESPACE = "qa-123-1-5ffd5b21-deadbeef"
MARKETS = {
    "BTC/EUR": {"market_id": 1, "change_24h": 1.5,
                "source_at": datetime(2026, 11, 8, 9, 12, tzinfo=timezone.utc)},
    "BTC/USDT": {"market_id": 2, "change_24h": -1.5,
                 "source_at": datetime(2026, 11, 8, 9, 12, tzinfo=timezone.utc)},
}


def _snapshot(eur_score, usdt_score, *, stale=False):
    rows = {
        "BTC/EUR": {"owner_id": 11, "market_id": 1,
                    "indicator_config": (("market", "change_24h"),),
                    "source_at": "2026-11-08T09:12:00Z",
                    "score": eur_score, "source_status": "stale_source" if stale else "fresh",
                    "source_reason": "stale_source" if stale else "fresh"},
        "BTC/USDT": {"owner_id": 11, "market_id": 2,
                     "indicator_config": (("market", "change_24h"),),
                     "source_at": "2026-11-08T09:12:00Z", "score": usdt_score,
                     "source_status": "fresh", "source_reason": "fresh"},
    }
    return {"pairs": rows}


def test_probe_runs_three_pair_snapshots_and_cleans_only_verified_fixture(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda namespace, owner: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: steps.append("seed_readings"))
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 70, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: deepcopy(next(snapshots)))
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, stale: steps.append(f"stale:{stale}"))
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "PASS", "failed_checks": [],
                                    "pairs": 2, "phases": 3,
                                    "source_outage": "owner_scoped", "live_calls": 0}
    assert steps == ["seed_readings", "stale:True", "stale:False", "cleanup"]


def test_probe_quarantines_on_score_cross_contamination(monkeypatch):
    monkeypatch.setenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", "1")
    monkeypatch.setenv("FINN_QA_USER_ID", "7")
    steps = []
    monkeypatch.setattr(probe, "_markets", lambda: MARKETS)
    monkeypatch.setattr(probe.fixture, "_seed", lambda *args: (11, 22, "today"))
    monkeypatch.setattr(probe, "_seed_pair_readings", lambda *args: None)
    snapshots = iter((_snapshot(45, 70), _snapshot(None, 45, stale=True), _snapshot(45, 70)))
    monkeypatch.setattr(probe, "_snapshot", lambda *args: next(snapshots))
    monkeypatch.setattr(probe, "_set_eur_source_time", lambda *args, **kwargs: None)
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *args: steps.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *args: steps.append("quarantine"))
    assert probe.run(NAMESPACE) == {"result": "FAIL",
                                    "failed_checks": ["outage_typed_and_isolated"]}
    assert steps == ["quarantine"]


def test_probe_rejects_missing_authorization_before_source_or_fixture(monkeypatch):
    monkeypatch.delenv("FINN_QA_ALLOW_TRADER_PAIR_FIXTURE", raising=False)
    monkeypatch.setattr(probe, "_markets", lambda: pytest.fail("unexpected source read"))
    with pytest.raises(RuntimeError, match="^trader_pair_fixture_not_authorized$"):
        probe.run(NAMESPACE)


def test_probe_error_category_does_not_export_database_details():
    assert profile_error_category(
        "trader_pair_score_continuity", RuntimeError("private fixture user 123")
    ) == "trader_pair_probe_runtime_error"
    assert profile_error_category(
        "trader_pair_score_continuity", RuntimeError("btc_pair_source_unavailable")
    ) == "btc_pair_source_unavailable"
