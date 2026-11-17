"""Bounded, read-only coaching for two explicitly named saved trade plans."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _number(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return format(number.normalize(), "f").replace(".", ",") if number.is_finite() else None


def _scope(read: dict[str, Any], scope: str) -> dict[str, Any] | None:
    return next((item for item in read.get("results") or []
                 if isinstance(item, dict) and item.get("scope") == scope
                 and item.get("status") == "completed"
                 and isinstance(item.get("data"), dict)), None)


def select_named_plans(
    inventory: dict[str, Any], *, assets: set[str], named_pairs: set[tuple[str, str]],
) -> tuple[list[dict[str, Any]], str | None]:
    """A named pair must never resolve to the open workspace's other quote."""
    item = _scope(inventory, "read_saved_setup_inventory")
    if item is None:
        return [], "Ik kan je opgeslagen plannen nu niet uitlezen. Probeer het later opnieuw; ik heb niets gewijzigd."
    rows = (item["data"].get("setups") or [])
    chosen: list[dict[str, Any]] = []
    for asset in sorted(assets):
        exact_quotes = {quote for symbol, quote in named_pairs if symbol == asset}
        candidates = [row for row in rows if isinstance(row, dict)
                      and str(row.get("symbol") or "").upper() == asset
                      and (not exact_quotes or str(row.get("pair") or "").upper()
                           in {f"{asset}/{quote}" for quote in exact_quotes})]
        if len(candidates) != 1:
            label = f"{asset}/{next(iter(exact_quotes))}" if len(exact_quotes) == 1 else asset
            if not candidates:
                return [], f"Ik vind geen uniek opgeslagen plan voor {label}. Ik heb niets gewijzigd."
            return [], f"Ik vind meerdere opgeslagen plannen voor {label}. Noem het plan dat je wilt beoordelen; ik heb niets gewijzigd."
        chosen.append(candidates[0])
    return chosen, None


def render_two_plan_checks(
    plans: list[dict[str, Any]], market_read: dict[str, Any],
    quote_reads: dict[int, dict[str, Any]],
) -> str:
    """One check per owner-bound plan, with no invented timeframe or entry rule."""
    market = _scope(market_read, "read_setup_market_matches")
    matches = (market["data"].get("matches") or []) if market else []
    parts = []
    for plan in plans:
        setup_id = plan.get("setup_id")
        symbol = str(plan.get("symbol") or "").upper()
        pair = str(plan.get("pair") or "").upper()
        label = pair or symbol
        name = str(plan.get("name") or label)
        timeframe = str(plan.get("timeframe") or "").upper()
        setup_type = str(plan.get("setup_type") or "").lower()
        kind = "trade-opzet" if setup_type == "trade" else "DCA-opzet" if setup_type == "dca" else "opzet"
        prefix = f"{label} — ‘{name}’ ({timeframe + ' ' if timeframe else ''}{kind}):"
        rows = [row for row in matches if isinstance(row, dict) and row.get("setup_id") == setup_id]
        match = rows[0] if len(rows) == 1 else {}
        low, high = _number(plan.get("min_benchmark_score")), _number(plan.get("max_benchmark_score"))
        score = _number(match.get("benchmark_score")) if match.get("source_status") == "available" else None
        quote_item = _scope(quote_reads.get(setup_id) or {}, "read_market_snapshot")
        quote_data = quote_item["data"] if quote_item else {}
        source_moment = quote_data.get("source_observed_at_amsterdam")
        if score is None:
            components = match.get("component_source_status") or {}
            missing = [label for key, label in (
                ("market_score", "Markt"), ("macro_score", "Macro"),
                ("technical_score", "Technisch"),
            ) if components.get(key) != "fresh"] if isinstance(components, dict) else []
            detail = ", ".join(missing) if missing else "benchmarkdeelscore of bronmeting"
            check = f"Controleer de ontbrekende of nog niet geverifieerde {detail}; de planmatch is nog niet bevestigd."
        elif low is not None and high is not None:
            value = Decimal(score.replace(",", "."))
            lower, upper = Decimal(low.replace(",", ".")), Decimal(high.replace(",", "."))
            relation = "binnen" if lower <= value <= upper else "buiten"
            check = (f"Controleer de uitgelezen benchmark {score}/100 tegenover je opgeslagen zone "
                     f"{low}–{high}: die ligt {relation} de zone. Dit is op zichzelf geen instapsignaal.")
        else:
            check = f"Controleer de uitgelezen benchmark {score}/100 tegen je overige opgeslagen voorwaarden. Dit is geen instapsignaal."
        if quote_item is None or quote_data.get("source_status") in {"unavailable", "missing", "no_data"}:
            check += " Een actuele koersbron voor dit exacte instrument kon ik niet bevestigen."
        elif source_moment:
            check += f" Koersbronmoment: {source_moment}."
        parts.append(f"{prefix} {check}")
    return " ".join(parts) + " Ik heb geen plan gewijzigd en geen order geplaatst."
