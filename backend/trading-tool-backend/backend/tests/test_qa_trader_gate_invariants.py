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


def test_source_time_parity_respects_only_finn_display_second_precision():
    canonical = "2026-11-08T23:59:59.876543+00:00"
    surfaces = {
        name: {"source_at": canonical, "displayed_at": canonical, "zone_label": "UTC"}
        for name in ("analysis", "report", "bot", "finn")
    }
    surfaces["finn"]["displayed_at"] = "2026-11-08T23:59:59+00:00"
    assert check_source_time_parity(canonical_source_at=canonical, surfaces=surfaces)["result"] == "PASS"
    surfaces["bot"]["displayed_at"] = "2026-11-08T23:59:59+00:00"
    assert "same_display_instant" in check_source_time_parity(
        canonical_source_at=canonical, surfaces=surfaces,
    )["failed_checks"]
    surfaces["bot"]["displayed_at"] = canonical
    surfaces["finn"]["source_at"] = "2026-11-08T23:59:59+00:00"
    assert "same_source_instant" in check_source_time_parity(
        canonical_source_at=canonical, surfaces=surfaces,
    )["failed_checks"]


def _pair(owner, market, score):
    return {
        "owner_id": owner, "market_id": market, "indicator_config": {"Price": 1},
        "source_at": "2026-11-08T09:12:00+00:00", "source_status": "fresh", "score": score,
    }


def test_pair_score_outage_and_recovery_do_not_cross_exact_markets():
    initial = {"pairs": {"BTC/EUR": _pair(7, 1, 45), "BTC/USDT": _pair(7, 2, 70)}}
    outage = deepcopy(initial)
    outage["pairs"]["BTC/EUR"].update(
        score=None, source_status="stale_source", fixture_source_diagnosis="stale_source",
        stale_reading_proven=True,
    )
    recovered = deepcopy(initial)
    assert check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered) == {
        "result": "PASS", "failed_checks": [],
    }
    outage["pairs"]["BTC/USDT"]["score"] = 45
    failed = check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered)
    assert failed["result"] == "FAIL"
    assert failed["failed_checks"] == ["outage_isolated"]
    assert "BTC/USDT" not in str(failed)


def test_pair_scores_reject_owner_crossing_and_missing_reason():
    initial = {"pairs": {"BTC/EUR": _pair(7, 1, 45), "BTC/USDT": _pair(7, 2, 70)}}
    outage = deepcopy(initial)
    outage["pairs"]["BTC/EUR"].update(score=None, source_status="stale_source")
    recovered = deepcopy(initial)
    recovered["pairs"]["BTC/USDT"]["owner_id"] = 8
    failed = check_pair_score_isolation(owner_id=7, initial=initial, outage=outage, recovered=recovered)
    assert set(failed["failed_checks"]) == {"owner_scope", "fixture_stale_cause_proven"}


def test_pair_missing_score_requires_independently_proven_stale_reading():
    initial = {"pairs": {"BTC/EUR": _pair(7, 1, 45), "BTC/USDT": _pair(7, 2, 70)}}
    outage = deepcopy(initial)
    outage["pairs"]["BTC/EUR"].update(
        score=None, source_status="missing_score", fixture_source_diagnosis="stale_source",
        stale_reading_proven=True,
    )
    recovered = deepcopy(initial)
    assert check_pair_score_isolation(
        owner_id=7, initial=initial, outage=outage, recovered=recovered,
    )["result"] == "PASS"
    outage["pairs"]["BTC/EUR"]["stale_reading_proven"] = False
    assert check_pair_score_isolation(
        owner_id=7, initial=initial, outage=outage, recovered=recovered,
    )["failed_checks"] == ["fixture_stale_cause_proven"]


def _exit():
    evidence = {
        "environment": "paper", "is_live": False, "live_calls": 0, "broker_orders": 0,
        "owner_scoped": True, "owner_active": False, "exchange_keys": 0,
        "order_count": 1, "execution_count": 1,
        "side": "sell", "status": "filled", "execution_source_currency": "USDT",
        "settlement_currency": "EUR", "execution_source_price": "100",
        "execution_fx_eur_per_unit": "0.9",
        "execution_source_at": "2026-11-08T09:12:00Z",
        "execution_fx_at": "2026-11-08T09:10:00Z",
        "execution_eur_price": "90", "order_price_eur": "90", "ledger_price_eur": "90",
        "quantity": "0.5", "quantity_before": "0.5", "quantity_after": "0",
        "order_quantity": "0.5", "ledger_qty_delta": "-0.5",
        "proceeds_eur": "45", "ledger_cash_delta_eur": "45",
        "order_amount_eur": "45", "order_id": 91, "ledger_order_id": 91,
        "cash_before_eur": "10", "cash_after_eur": "55",
    }
    evidence["history_projection"] = {key: evidence[key] for key in (
        "execution_source_currency", "execution_source_at", "execution_fx_at",
        "quantity", "execution_eur_price", "proceeds_eur"
    )}
    return evidence


def test_paper_exit_reconciles_without_exporting_prices_or_fixture_identity():
    evidence = _exit()
    assert check_paper_exit(evidence) == {"result": "PASS", "failed_checks": []}
    evidence["ledger_cash_delta_eur"] = "44"
    evidence["history_projection"]["quantity"] = "0.4"
    failed = check_paper_exit(evidence)
    assert set(failed["failed_checks"]) == {
        "cashflow_reconciles", "bot_history_projection_reconciles"
    }
    assert "44" not in str(failed) and "0.4" not in str(failed)


def test_paper_exit_rejects_live_execution_and_undated_source():
    evidence = _exit()
    evidence["is_live"] = True
    evidence["execution_source_at"] = "2026-11-08T09:12:00"
    failed = check_paper_exit(evidence)
    assert set(failed["failed_checks"]) == {
        "paper_only", "dated_sources", "bot_history_projection_reconciles"
    }


def test_paper_exit_uses_execution_quote_when_decision_quote_has_moved():
    evidence = _exit()
    evidence["decision_source_price"] = "95"
    evidence["decision_fx_eur_per_unit"] = "0.88"
    evidence["decision_source_at"] = "2026-11-08T09:00:00Z"
    assert check_paper_exit(evidence)["result"] == "PASS"
    evidence["execution_source_price"] = "110"
    assert check_paper_exit(evidence)["failed_checks"] == ["source_conversion"]


def test_paper_exit_rejects_corrupt_order_and_ledger_reconciliation():
    evidence = _exit()
    evidence.update(order_quantity="0.4", ledger_qty_delta="-0.4",
                    order_amount_eur="44", ledger_order_id=92)
    assert set(check_paper_exit(evidence)["failed_checks"]) == {
        "quantity_reconciles", "cashflow_reconciles", "order_ledger_link"
    }
