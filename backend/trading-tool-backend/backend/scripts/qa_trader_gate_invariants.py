"""Pure, sanitized invariants for protected trader-gate QA evidence.

Collectors must obtain all inputs from the protected fixture and must not
include private values in the returned verdict. This module has no I/O.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


def _result(checks: dict[str, bool]) -> dict[str, Any]:
    failed = [name for name, passed in checks.items() if not passed]
    return {"result": "FAIL" if failed else "PASS", "failed_checks": failed}


def _decimal(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number.is_finite() else None


def _near(left: Any, right: Any, tolerance: str) -> bool:
    a, b = _decimal(left), _decimal(right)
    return a is not None and b is not None and abs(a - b) <= Decimal(tolerance)


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return instant.astimezone(timezone.utc) if instant.tzinfo else None


def check_account_state(*, owner_id: int, authoritative: dict, turns: list[dict]) -> dict[str, Any]:
    """Require three read-only turns to match independently stored facts."""
    kinds = ("plan", "bot", "position", "latest_decision")
    complete = len(turns) == 3 and set(authoritative) == set(kinds) and all(
        isinstance(authoritative[kind], dict) for kind in kinds
    ) and all(
        isinstance(turn, dict) and isinstance(turn.get("facts"), dict)
        and set(turn["facts"]) == set(kinds)
        and all(isinstance(turn["facts"][kind], dict) for kind in kinds)
        for turn in turns
    )
    if not complete:
        return _result({"complete_account_state": False})
    owner_scoped = all(
        fact.get("owner_id") == owner_id
        for fact in authoritative.values() if isinstance(fact, dict)
    ) and all(
        fact.get("owner_id") == owner_id
        for turn in turns for fact in turn["facts"].values() if isinstance(fact, dict)
    )
    source_identical = all(
        turn["facts"][kind].get("source_id") == authoritative[kind].get("source_id")
        for turn in turns for kind in kinds
    )
    facts_identical = all(
        turn["facts"][kind].get("fields") == authoritative[kind].get("fields")
        for turn in turns for kind in kinds
    ) and all(
        authoritative[kind].get("source_id") is None
        or isinstance(authoritative[kind].get("fields"), dict) and bool(authoritative[kind]["fields"])
        for kind in kinds
    )
    missing_typed = all(
        authoritative[kind].get("source_id") is not None
        or all(turn["facts"][kind].get("missing_reason") == authoritative[kind].get("missing_reason")
               and bool(turn["facts"][kind].get("missing_reason")) for turn in turns)
        for kind in kinds
    )
    read_only = all(
        turn.get("proposal_count") == 0 and turn.get("execution_count") == 0
        for turn in turns
    )
    return _result({
        "owner_scope": owner_scoped,
        "verified_source_refs": source_identical,
        "saved_facts_match": facts_identical,
        "missing_source_typed": missing_typed,
        "read_only": read_only,
    })


def check_source_time_parity(*, canonical_source_at: str, surfaces: dict) -> dict[str, Any]:
    """Require four explicit-zone presentations of one source instant."""
    required = {"analysis", "report", "bot", "finn"}
    if set(surfaces) != required:
        return _result({"four_surfaces_present": False})
    canonical = _utc(canonical_source_at)
    all_present = canonical is not None and all(
        isinstance(item, dict) and _utc(item.get("source_at")) is not None
        and _utc(item.get("displayed_at")) is not None
        for item in surfaces.values()
    )
    same_source = bool(all_present) and all(
        _utc(item["source_at"]) == canonical for item in surfaces.values()
    )
    same_display = bool(all_present) and all(
        _utc(item["displayed_at"]) == canonical for item in surfaces.values()
    )
    zone_offsets = {"UTC": 0, "CET": 3600, "CEST": 7200}
    explicit_zone = all(
        isinstance(item, dict) and item.get("zone_label") in zone_offsets
        and _utc(item.get("displayed_at")) is not None
        and datetime.fromisoformat(item["displayed_at"].replace("Z", "+00:00")).utcoffset().total_seconds()
            == zone_offsets[item["zone_label"]]
        for item in surfaces.values()
    )
    return _result({
        "dated_source": bool(all_present),
        "same_source_instant": same_source,
        "same_display_instant": same_display,
        "explicit_zone": explicit_zone,
    })


def check_pair_score_isolation(
    *, owner_id: int, initial: dict, outage: dict, recovered: dict,
) -> dict[str, Any]:
    """Check two exact BTC markets across an owner-scoped source outage."""
    names = ("BTC/EUR", "BTC/USDT")
    snapshots = (initial, outage, recovered)
    rows = [snapshot.get("pairs", {}) for snapshot in snapshots]
    present = all(set(pair_rows) == set(names) for pair_rows in rows)
    if not present:
        return _result({"both_pairs_present": False})
    eur = [pair_rows[names[0]] for pair_rows in rows]
    usdt = [pair_rows[names[1]] for pair_rows in rows]
    owner_scoped = all(
        row.get("owner_id") == owner_id for pair in (eur, usdt) for row in pair
    )
    identities = all(
        pair[0].get("market_id") == pair[1].get("market_id") == pair[2].get("market_id")
        for pair in (eur, usdt)
    ) and eur[0].get("market_id") != usdt[0].get("market_id")
    configs = all(
        pair[0].get("indicator_config") == pair[1].get("indicator_config") == pair[2].get("indicator_config")
        for pair in (eur, usdt)
    )
    dated = all(_utc(row.get("source_at")) for pair in (eur, usdt) for row in (pair[0], pair[2]))
    baseline = all(pair[0].get("source_status") == "fresh" and _decimal(pair[0].get("score")) is not None
                   for pair in (eur, usdt))
    distinct = _decimal(eur[0].get("score")) != _decimal(usdt[0].get("score"))
    outage_safe = (
        eur[1].get("score") is None
        and eur[1].get("source_status") in {"stale_source", "missing_indicator_reading", "score_rebuild_pending"}
        and eur[1].get("source_reason") in {"stale_source", "source_unavailable", "insufficient_indicator_history"}
        and usdt[1].get("score") == usdt[0].get("score")
        and usdt[1].get("source_status") == "fresh"
    )
    recovery = (
        eur[2].get("source_status") == "fresh"
        and _decimal(eur[2].get("score")) is not None
        and _utc(eur[2].get("source_at")) is not None
        and _utc(eur[0].get("source_at")) is not None
        and _utc(eur[2].get("source_at")) >= _utc(eur[0].get("source_at"))
        and usdt[2].get("score") == usdt[0].get("score")
        and usdt[2].get("source_status") == "fresh"
    )
    return _result({
        "owner_scope": owner_scoped,
        "exact_market_identity": identities,
        "configuration_stable": configs,
        "dated_sources": bool(dated),
        "initial_scores_verified": baseline,
        "pair_scores_distinct": distinct,
        "outage_typed_and_isolated": outage_safe,
        "recovery_isolated": recovery,
    })


def check_paper_exit(evidence: dict) -> dict[str, Any]:
    """Reconcile one automatic Paper sell with its UI and persisted cash leg."""
    source, factor = _decimal(evidence.get("source_price")), _decimal(evidence.get("fx_eur_per_unit"))
    eur_price, qty = _decimal(evidence.get("execution_eur_price")), _decimal(evidence.get("quantity"))
    proceeds = _decimal(evidence.get("proceeds_eur"))
    before_cash = _decimal(evidence.get("cash_before_eur"))
    after_cash = _decimal(evidence.get("cash_after_eur"))
    before_qty = _decimal(evidence.get("quantity_before"))
    after_qty = _decimal(evidence.get("quantity_after"))
    ui = evidence.get("ui") if isinstance(evidence.get("ui"), dict) else {}
    checks = {
        "paper_only": evidence.get("environment") == "paper" and evidence.get("is_live") is False
                      and evidence.get("live_calls") == 0 and evidence.get("broker_orders") == 0,
        "owner_scope": evidence.get("owner_scoped") is True and evidence.get("owner_active") is False
                       and evidence.get("exchange_keys") == 0,
        "single_filled_sell": evidence.get("order_count") == 1 and evidence.get("execution_count") == 1
                              and evidence.get("side") == "sell" and evidence.get("status") == "filled",
        "dated_sources": _utc(evidence.get("source_at")) is not None and _utc(evidence.get("fx_at")) is not None,
        "currency_recorded": evidence.get("source_currency") in {"EUR", "USDT"}
                             and evidence.get("settlement_currency") == "EUR",
        "source_conversion": source is not None and factor is not None and eur_price is not None
                             and _near(eur_price, source * factor, "0.000001"),
        "order_ledger_price": _near(evidence.get("order_price_eur"), eur_price, "0.000001")
                              and _near(evidence.get("ledger_price_eur"), eur_price, "0.000001"),
        "quantity_reconciles": qty is not None and qty > 0 and before_qty is not None and after_qty is not None
                               and _near(before_qty - after_qty, qty, "0.00000001"),
        "cashflow_reconciles": qty is not None and eur_price is not None and proceeds is not None
                               and before_cash is not None and after_cash is not None
                               and _near(proceeds, (qty * eur_price).quantize(Decimal("0.01")), "0.01")
                               and _near(after_cash - before_cash, proceeds, "0.01")
                               and _near(evidence.get("ledger_cash_delta_eur"), proceeds, "0.01"),
        "ui_reconciles": all(key in ui and ui[key] is not None and ui[key] == evidence.get(key) for key in (
            "source_currency", "source_at", "fx_at", "quantity", "execution_eur_price", "proceeds_eur"
        )),
    }
    return _result(checks)
