"""Bounded, read-only coaching for two explicitly named saved trade plans."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from backend.services.asset_catalog_service import mentioned_catalog_symbols


def is_preparation_followup(message: str) -> bool:
    """Distinguish today's preparation from an initial plan assessment."""
    return bool(re.search(
        r"\b(?:voorbereiding|voorbereiden|alleen\s+wachten)\b.*\b(?:vandaag|verbeter\w*|controle\w*)\b"
        r"|\b(?:vandaag|verbeter\w*)\b.*\bvoorbereid\w*\b",
        str(message or ""), re.I | re.S,
    ))


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
    *, preparation: bool = False,
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
            check = (f"Controleer vandaag in Analyse of de ontbrekende of nog niet geverifieerde {detail} "
                     "voor dit exacte plan een "
                     "geverifieerde score en bronmoment heeft; de planmatch is nog niet bevestigd."
                     if preparation else
                     f"Controleer de ontbrekende of nog niet geverifieerde {detail}; de planmatch is nog niet bevestigd.")
        elif low is not None and high is not None:
            value = Decimal(score.replace(",", "."))
            lower, upper = Decimal(low.replace(",", ".")), Decimal(high.replace(",", "."))
            relation = "binnen" if lower <= value <= upper else "buiten"
            check = (f"Controleer bij de volgende scoreverversing voor dit exacte plan of "
                     f"de benchmark van {score}/100 naar je opgeslagen zone {low}–{high} beweegt; "
                     f"hij ligt nu {relation} de zone. Dit bevestigt geen instap."
                     if preparation else
                     f"Controleer de uitgelezen benchmark {score}/100 tegenover je opgeslagen zone "
                     f"{low}–{high}: die ligt {relation} de zone. Dit is op zichzelf geen instapsignaal.")
        else:
            check = (f"Controleer vandaag de benchmark {score}/100 tegen de overige opgeslagen "
                     "planvoorwaarden. Dit bevestigt geen instap." if preparation else
                     f"Controleer de uitgelezen benchmark {score}/100 tegen je overige opgeslagen voorwaarden. Dit is geen instapsignaal.")
        if quote_item is None or quote_data.get("source_status") in {"unavailable", "missing", "no_data"}:
            check += " Een actuele koersbron voor dit exacte instrument kon ik niet bevestigen."
        elif source_moment:
            check += f" Koersbronmoment: {source_moment}."
        parts.append(f"{prefix} {check}")
    intro = "Je kunt je voorbereiding vandaag verbeteren zonder een trade te forceren. " if preparation else ""
    return intro + " ".join(parts) + " Ik heb geen plan gewijzigd en geen order geplaatst."


def verified_two_plan_checks(message: str, calls: tuple[dict[str, Any], ...]) -> str | None:
    """Rebuild the answer only from the exact reads made by the trusted route."""
    if not calls or calls[0].get("name") != "get_saved_setup_inventory":
        return None
    inventory = calls[0].get("result")
    if not isinstance(inventory, dict) or calls[0].get("arguments") not in ({}, None):
        return None
    assets = mentioned_catalog_symbols(message)
    if len(assets) != 2:
        return None
    named_pairs = {
        (asset.upper(), quote.upper())
        for asset, quote in re.findall(r"\b([A-Z]{2,10})/(EUR|USDT)\b", message, re.I)
        if asset.upper() in assets
    }
    plans, error = select_named_plans(inventory, assets=assets, named_pairs=named_pairs)
    if error is not None:
        return error if len(calls) == 1 else None
    if len(calls) != 2 + len(plans) or calls[1].get("name") != "get_setup_market_matches":
        return None
    market_read = calls[1].get("result")
    if calls[1].get("arguments") not in ({}, None) or not isinstance(market_read, dict):
        return None
    selected_ids = (inventory.get("turn_request") or {}).get("target_ids")
    if selected_ids != [plan.get("setup_id") for plan in plans]:
        return None
    quote_reads = {}
    expected_pairs = set()
    for plan in plans:
        symbol = str(plan.get("symbol") or "").upper()
        pair = str(plan.get("pair") or "").upper()
        quote = pair.split("/", 1)[1] if pair.startswith(f"{symbol}/") else str(plan.get("quote_currency") or "").upper()
        expected_pairs.add((symbol, quote))
    seen_pairs = set()
    for call in calls[2:]:
        if call.get("name") != "get_market_snapshot" or not isinstance(call.get("result"), dict):
            return None
        args = call.get("arguments") or {}
        pair = (str(args.get("asset") or "").upper(), str(args.get("quote_currency") or "").upper())
        if pair not in expected_pairs or pair in seen_pairs:
            return None
        plan = next(row for row in plans if str(row.get("symbol") or "").upper() == pair[0])
        quote_reads[plan["setup_id"]] = call["result"]
        seen_pairs.add(pair)
    if seen_pairs != expected_pairs:
        return None
    return render_two_plan_checks(plans, market_read, quote_reads,
                                  preparation=is_preparation_followup(message))
