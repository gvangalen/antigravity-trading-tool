"""Read-only coaching from one owner-scoped plan, score and Paper snapshot."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _number(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f").replace(".", ",")


def render_fomo_plan_answer(read_result: dict[str, Any], *, asset: str) -> str:
    """Never turn a partial benchmark or bot budget into buy permission."""
    rows = {
        item.get("scope"): item
        for item in read_result.get("results") or []
        if isinstance(item, dict) and item.get("scope") in {
            "read_active_setup", "read_linked_strategy", "read_asset_scores",
            "read_market_snapshot", "read_portfolio",
        }
    }
    missing = [name for name, scope in (
        ("opgeslagen setup", "read_active_setup"),
        ("gekoppelde strategie", "read_linked_strategy"),
        ("actuele scores", "read_asset_scores"),
        ("Paper-portefeuille", "read_portfolio"),
    ) if rows.get(scope, {}).get("status") != "completed"
        or not isinstance(rows[scope].get("data"), dict)]
    if missing:
        return ("Ik kan je aankoopvraag nog niet aan je eigen gegevens toetsen: "
                + ", ".join(missing) + " niet eenduidig uitgelezen. "
                "Dit is geen instapsignaal; ik heb niets voorgesteld of uitgevoerd.")

    setup = rows["read_active_setup"]["data"]
    strategy = rows["read_linked_strategy"]["data"]
    scores = rows["read_asset_scores"]["data"]
    portfolio = rows["read_portfolio"]["data"]
    if (str(setup.get("symbol") or "").upper() != asset
            or strategy.get("setup_id") != setup.get("setup_id")
            or str(scores.get("symbol") or "").upper() != asset
            or portfolio.get("environment") != "paper"):
        return ("Ik kan de opgeslagen setup, scores en Paper-portefeuille niet "
                "eenduidig aan dezelfde asset koppelen. Ik kan daarom geen "
                "instapsignaal bevestigen; er is niets voorgesteld of uitgevoerd.")

    setup_type = str(setup.get("setup_type") or "").lower()
    kind = {"trade": "trade-opzet", "dca": "DCA-opzet"}.get(setup_type, "opzet")
    name = str(setup.get("name") or asset)
    low, high = _number(setup.get("min_benchmark_score")), _number(setup.get("max_benchmark_score"))
    zone = f" met benchmarkzone {low}–{high}" if low is not None and high is not None else ""
    parts = [f"Je opgeslagen {asset}-setup ‘{name}’ is een {kind}{zone}."]
    amount = _number(strategy.get("base_amount"))
    currency = str(strategy.get("currency") or "").upper()
    if amount is not None and currency in {"EUR", "USD", "USDT"}:
        parts.append(f"De gekoppelde strategie heeft een opgeslagen uitvoeringsbedrag van {amount} {currency}; dat is geen afzonderlijke toestemming om bij te kopen.")

    reported = scores.get("reported_scores") or {}
    if not isinstance(reported, dict):
        reported = {}
    labels = (("Markt", "market_score"), ("Macro", "macro_score"), ("Technisch", "technical_score"))
    parts.append("De uitgelezen scores: " + ", ".join(
        f"{label} {_number(reported.get(key))}/100" if _number(reported.get(key)) is not None
        else f"{label} zonder bevestigde score"
        for label, key in labels
    ) + ".")
    benchmark = _number(scores.get("benchmark_score"))
    incomplete_scores = benchmark is None or any(reported.get(key) is None for _, key in labels)
    if incomplete_scores:
        parts.append("De totale benchmark en een match met je setupzone zijn daardoor niet bevestigd.")
    else:
        parts.append(f"De uitgelezen totale benchmark is {benchmark}/100; een score alleen is geen instapsignaal.")
        if low is not None and high is not None:
            score_value = Decimal(benchmark.replace(",", "."))
            lower, upper = Decimal(low.replace(",", ".")), Decimal(high.replace(",", "."))
            if score_value < lower or score_value > upper:
                parts.append(f"Deze score ligt buiten de opgeslagen setupzone {low}–{high}; de scorevoorwaarde is niet voldaan.")
            else:
                parts.append(f"Deze score ligt binnen de opgeslagen setupzone {low}–{high}, maar bevestigt op zichzelf geen instap.")

    def same_plan_bot(row: dict[str, Any]) -> bool:
        setup_id, strategy_id = row.get("setup_id"), row.get("strategy_id")
        return (setup_id is not None or strategy_id is not None) and (
            setup_id is None or setup_id == setup.get("setup_id")
        ) and (
            strategy_id is None or strategy_id == strategy.get("strategy_id")
        )

    paper_rows = [row for row in portfolio.get("bots") or [] if isinstance(row, dict)
                  and str(row.get("symbol") or "").upper() == asset
                  and row.get("is_live") is False
                  and same_plan_bot(row)]
    if len(paper_rows) == 1:
        row = paper_rows[0]
        qty, cash = _number(row.get("position_qty")), _number(row.get("paper_cash_eur"))
        if qty is not None:
            parts.append(f"De Paper-bot heeft {qty} {asset} open.")
        if cash is not None:
            parts.append(f"De uitgelezen Paper-kas voor deze bot is €{cash}.")
        budget = _number(row.get("budget_total_eur"))
        if row.get("budget_limit_enabled") is True and budget is not None:
            parts.append(f"De botlimiet is €{budget}, geen extra koopruimte.")
    else:
        parts.append("Ik kan uit deze portefeuillelezing geen unieke Paper-botpositie voor deze setup bevestigen.")

    quote = rows.get("read_market_snapshot") or {}
    quote_fresh = quote.get("status") == "completed" and quote.get("freshness") == "fresh"
    if quote.get("status") == "completed":
        moment = (quote.get("data") or {}).get("source_observed_at_amsterdam")
        if moment:
            parts.append(f"Het laatste uitgelezen koersbronmoment is {moment}.")
        if not quote_fresh:
            parts.append("Deze koers is niet bevestigd als actuele uitvoeringskoers.")
    else:
        parts.append("Een actuele uitvoeringskoers is niet geverifieerd.")
    next_checks = []
    if incomplete_scores:
        next_checks.append("een complete actuele score")
    if not quote_fresh:
        next_checks.append("een bevestigde actuele koers")
    if next_checks:
        parts.append("Wacht op " + " en ".join(next_checks) + ".")
    parts.append("Een aankoop uit FOMO is geen instapsignaal bij deze gegevens. Toets daarna de opgeslagen voorwaarden en risico's. Ik heb geen koopvoorstel gemaakt en niets uitgevoerd.")
    return " ".join(parts)
