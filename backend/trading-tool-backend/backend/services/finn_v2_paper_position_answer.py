"""Answer a narrow Paper position and cash question from one owner-scoped read."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any


PAPER_POSITION_CASH_UNAVAILABLE = (
    "Ik kan de actuele Paper-positie en kas voor deze bot niet eenduidig "
    "verifiëren. Het botbudget is geen extra koopruimte; controleer de "
    "Paper-portefeuille en risicogrenzen voordat je een aankoop beoordeelt."
)


def _amount(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return format(number.normalize(), "f").replace(".", ",")


def render_paper_position_cash_answer(
    message: str, tool_trace: tuple[dict[str, Any], ...], *, asset: str, locale: str,
) -> str | None:
    """Never equate a bot budget with additional spending power."""
    if (not locale.lower().startswith("nl") or not asset
            or not re.search(r"\b(?:positie|posities)\b", message, re.I)
            or not re.search(r"\b(?:kas|kassaldo|cash|saldo)\b", message, re.I)
            or not re.search(r"\bbotbudget\b", message, re.I)):
        return None
    for call in reversed(tool_trace):
        for item in reversed((call.get("result") or {}).get("results") or []):
            if (not isinstance(item, dict) or item.get("scope") != "read_portfolio"
                    or item.get("status") != "completed"):
                continue
            data = item.get("data") or {}
            if data.get("environment") != "paper" or not isinstance(data.get("bots"), list):
                continue
            rows = [row for row in data["bots"] if isinstance(row, dict)
                    and str(row.get("symbol") or "").upper() == asset.upper()
                    and row.get("is_live") is False]
            if len(rows) > 1:
                named_budget = re.search(r"\bbotbudget\b[^.!?]{0,25}?€\s*(\d+(?:[.,]\d+)?)", message, re.I)
                if named_budget:
                    try:
                        requested_budget = Decimal(named_budget.group(1).replace(",", "."))
                    except InvalidOperation:
                        requested_budget = None
                    if requested_budget is not None:
                        rows = [row for row in rows if _amount(row.get("budget_total_eur")) ==
                                format(requested_budget.normalize(), "f").replace(".", ",")]
            if len(rows) != 1:
                continue
            row = rows[0]
            quantity = _amount(row.get("position_qty"))
            cash = _amount(row.get("paper_cash_eur"))
            budget = _amount(row.get("budget_total_eur"))
            if quantity is None or cash is None or budget is None:
                continue
            return (
                f"Volgens de uitgelezen Paper-portefeuille heeft je {asset.upper()}-bot "
                f"{quantity} {asset.upper()} open en €{cash} Paper-kas. "
                f"Het opgeslagen botbudget is €{budget}; dat is geen extra koopruimte. "
                "Of een nieuwe aankoop mogelijk is, hangt ook af van de actuele "
                "uitvoeringskoers, beschikbare kas en de ingestelde risicogrenzen."
            )
    return None
