"""Source-bound recovery for a read-only, single-asset coach answer.

This is used only after a model answer fails source-moment verification. It
reports the current turn's owner-scoped reads separately and never invents a
trade recommendation or treats a missing read as a current value.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment


def _number(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite():
        return None
    return format(number.normalize(), "f").replace(".", ",")


def _rows(evidence: tuple[dict[str, Any], ...], scope: str, asset: str) -> list[dict[str, Any]]:
    rows = []
    for item in evidence:
        if item.get("scope") != scope or item.get("status") != "completed":
            continue
        data = item.get("data")
        if not isinstance(data, dict):
            continue
        symbol = str(data.get("symbol") or data.get("asset") or item.get("asset") or "").upper()
        if symbol and symbol.split("/", 1)[0] != asset:
            continue
        rows.append(data)
    return rows


def render_coach_source_fallback(
    *, asset: str, topics: tuple[str, ...], evidence: tuple[dict[str, Any], ...],
) -> str | None:
    """Compose only requested topics from completed reads of the current turn."""
    if not asset or not topics or not evidence:
        return None
    lines = [f"Ik heb de bronnen voor {asset} afzonderlijk gecontroleerd:"]
    verified = False
    for topic in topics:
        if topic == "setup":
            setups = _rows(evidence, "read_active_setup", asset)
            strategies = _rows(evidence, "read_linked_strategy", asset)
            if len(setups) == 1:
                setup = setups[0]
                name = str(setup.get("name") or "naam onbekend")
                band = ""
                minimum = _number(setup.get("min_benchmark_score"))
                maximum = _number(setup.get("max_benchmark_score"))
                if minimum and maximum:
                    band = f", scoreband {minimum}–{maximum}"
                strategy = (f"; gekoppelde strategie ‘{strategies[0]['name']}’"
                            if len(strategies) == 1 and strategies[0].get("name") else "")
                lines.append(f"- Plan: opgeslagen setup ‘{name}’{band}{strategy}.")
                verified = True
            else:
                lines.append("- Plan: geen eenduidige opgeslagen setup uitgelezen.")
        elif topic == "score":
            scores = _rows(evidence, "read_asset_scores", asset)
            score = _number(scores[0].get("benchmark_score")) if len(scores) == 1 else None
            if score:
                source = (scores[0].get("oldest_indicator_source_observed_at") or
                          scores[0].get("as_of"))
                at = amsterdam_source_moment(source)
                lines.append(f"- Benchmarkscore: {score} volgens de gelezen scorebron"
                             + (f"; oudste indicatorbron {at}." if at else "; bronmoment onbekend."))
                verified = True
            else:
                lines.append("- Benchmarkscore: geen verifieerbare actuele score uitgelezen.")
        elif topic == "bot":
            history = _rows(evidence, "read_review_history", asset)
            decisions = [row for data in history for row in data.get("latest_bot_decisions") or []
                         if isinstance(row, dict)
                         and str(row.get("symbol") or "").upper().split("/", 1)[0] == asset]
            if len(decisions) == 1:
                decision = decisions[0]
                at = amsterdam_source_moment(decision.get("decision_at"))
                reason = str(decision.get("safety_reason") or "").strip()
                lines.append(
                    f"- Botbeslissing: {decision.get('action') or 'actie onbekend'}"
                    + (f" op {at}" if at else " op een onbekend bronmoment")
                    + (f"; opgeslagen reden: {reason}." if reason else
                       "; geen concrete reden in de gelezen beslissing.")
                )
                verified = True
            else:
                lines.append("- Botbeslissing: geen eenduidig opgeslagen besluit uitgelezen.")
        elif topic == "report":
            reports = _rows(evidence, "read_latest_report", asset)
            at = amsterdam_source_moment(reports[0].get("generated_at")) if len(reports) == 1 else None
            if at:
                lines.append(f"- Dagrapport: momentopname van {at}.")
                verified = True
            else:
                lines.append("- Dagrapport: geen eenduidig rapportmoment uitgelezen.")
        elif topic == "quote":
            quotes = _rows(evidence, "read_market_snapshot", asset)
            quote = quotes[0] if len(quotes) == 1 else {}
            price = _number(quote.get("price"))
            at = amsterdam_source_moment(quote.get("source_observed_at") or
                                         quote.get("source_observed_at_utc") or
                                         quote.get("source_at") or quote.get("timestamp"))
            if price and at:
                currency = str(quote.get("quote_currency") or "").upper()
                lines.append(f"- Koers: {price} {currency}, bronmoment {at}.")
                verified = True
            else:
                lines.append("- Koers: geen actuele koers met controleerbaar bronmoment uitgelezen.")
        elif topic == "portfolio":
            portfolios = _rows(evidence, "read_portfolio", asset)
            portfolio = portfolios[0] if len(portfolios) == 1 else {}
            global_data = portfolio.get("global") or {}
            cash = _number(global_data.get("cash_balance"))
            at = amsterdam_source_moment(portfolio.get("read_at"))
            if cash:
                lines.append(f"- Paper-portefeuille: kas €{cash}"
                             + (f", uitgelezen op {at}." if at else ", uitleesmoment onbekend."))
                verified = True
            else:
                lines.append("- Paper-portefeuille: geen controleerbare kas uitgelezen.")
    if not verified:
        return None
    lines.append("Deze bronnen hebben eigen tijdstippen. Controleer een verse score, koers en botreden "
                 "voordat je handelt of instellingen wijzigt.")
    return "\n".join(lines)
