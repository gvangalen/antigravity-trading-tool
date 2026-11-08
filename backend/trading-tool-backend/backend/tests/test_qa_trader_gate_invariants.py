"""Synthetic, secret-free checks for future protected trader-gate collectors."""

from copy import deepcopy

from backend.scripts.qa_trader_gate_invariants import (
    check_account_state,
    check_pair_score_isolation,
    check_paper_exit,
    check_source_time_parity,
)


def test_account_state_requires_three_owner_scoped_read_only_turns():
    kinds = ("plan", "bot", "position", "latest_decision")
    saved = {kind: {"owner_id": 7, "source_id": index, "fields": {"state": kind}}
             for index, kind in enumerate(kinds, 1)}
    turns = [{"facts": deepcopy(saved), "proposal_count": 0, "execution_count": 0} for _ in range(3)]
    assert check_account_state(owner_id=7, authoritative=saved, turns=turns)["result"] == "PASS"
    turns[1]["facts"]["bot"]["fields"]["state"] = "different"
    turns[2]["facts"]["plan"]["owner_id"] = 8
    failed = check_account_state(owner_id=7, authoritative=saved, turns=turns)
    assert set(failed["failed_checks"]) == {"owner_scope", "saved_facts_match"}
    assert "different" not in str(failed)


def test_source_time_parity_requires_explicit_zone_and_same_instant():
    canonical = "2026-11-08T09:12:00Z"
    surfaces = {name: {"source_at": canonical, "displayed_at": canonical, "zone_label": "UTC"}
                for name in ("analysis", "report", "bot", "finn")}
    surfaces["bot"]["displayed_at"] = "2026-11-08T10:12:00+01:00"
    surfaces["bot"]["zone_label"] = "CET"
    assert check_source_time_parity(canonical_source_at=canonical, surfaces=surfaces)["result"] == "PASS"
    surfaces["analysis"]["zone_label"] = None
    surfaces["finn"]["displayed_at"] = "2026-11-08T10:12:00Z"
    failed = check_source_time_parity(canonical_source_at=canonical, surfaces=surfaces)
    assert set(failed["failed_checks"]) == {"same_display_instant", "explicit_zone"}
    surfaces["analysis"]["zone_label"] = "UTC"
    surfaces["finn"]["displayed_at"] = canonical
    surfaces["bot"]["zone_label"] = "CEST"
    assert check_source_time_parity(canonical_source_at=canonical, surfaces=surfaces)["failed_checks"] == ["explicit_zone"]


def _pair(owner, market, score):
    return {
        "owner_id": owner, "market_id": market, "indicator_config": {"Price": 1},
        "source_at": "2026-11-08T09:12:00+00:00", "source_status": "fresh", "score": score,
    }


def test_pair_score_outage_and_recovery_do_not_cross_exact_markets():
    initial = {"pairs": {"BTC/EUR": _pair(7, 1, 45), "BTC/USDT": _pair(7, 2, 70)}}
    outage = deepcopy(initial)
    outage["pairs"]["BTC/EUR"].update(score=None, source_status="stale_source", source_reason="stale_source")
    recovered = deepcopy(initial)
    assert check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered) == {
        "result": "PASS", "failed_checks": [],
    }
    outage["pairs"]["BTC/USDT"]["score"] = 45
    failed = check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered)
    assert failed["result"] == "FAIL"
    assert failed["failed_checks"] == ["outage_typed_and_isolated"]
    assert "BTC/USDT" not in str(failed)


def test_pair_scores_reject_owner_crossing_and_missing_reason():
    initial = {"pairs": {"BTC/EUR": _pair(7, 1, 45), "BTC/USDT": _pair(7, 2, 70)}}
    outage = deepcopy(initial)
    outage["pairs"]["BTC/EUR"].update(score=None, source_status="stale_source")
    recovered = deepcopy(initial)
    recovered["pairs"]["BTC/USDT"]["owner_id"] = 8
    failed = check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered)
    assert set(failed["failed_checks"]) == {"owner_scope", "outage_typed_and_isolated"}


def _exit():
    evidence = {
        "environment": "paper", "is_live": False, "live_calls": 0, "broker_orders": 0,
        "owner_scoped": True, "owner_active": False, "exchange_keys": 0,
        "order_count": 1, "execution_count": 1,
        "side": "sell", "status": "filled", "source_currency": "USDT",
        "settlement_currency": "EUR", "source_price": "100", "fx_eur_per_unit": "0.9",
        "source_at": "2026-11-08T09:12:00Z", "fx_at": "2026-11-08T09:10:00Z",
        "execution_eur_price": "90", "order_price_eur": "90", "ledger_price_eur": "90",
        "quantity": "0.5", "quantity_before": "0.5", "quantity_after": "0",
        "proceeds_eur": "45", "ledger_cash_delta_eur": "45",
        "cash_before_eur": "10", "cash_after_eur": "55",
    }
    evidence["ui"] = {key: evidence[key] for key in (
        "source_currency", "source_at", "fx_at", "quantity", "execution_eur_price", "proceeds_eur"
    )}
    return evidence


def test_paper_exit_reconciles_without_exporting_prices_or_fixture_identity():
    evidence = _exit()
    assert check_paper_exit(evidence) == {"result": "PASS", "failed_checks": []}
    evidence["ledger_cash_delta_eur"] = "44"
    evidence["ui"]["quantity"] = "0.4"
    failed = check_paper_exit(evidence)
    assert set(failed["failed_checks"]) == {"cashflow_reconciles", "ui_reconciles"}
    assert "44" not in str(failed) and "0.4" not in str(failed)


def test_paper_exit_rejects_live_execution_and_undated_source():
    evidence = _exit()
    evidence["is_live"] = True
    evidence["source_at"] = "2026-11-08T09:12:00"
    failed = check_paper_exit(evidence)
    assert set(failed["failed_checks"]) == {"paper_only", "dated_sources", "ui_reconciles"}
