"""State a saved strategy amount only when an owner-bound read proves it."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any


_AMOUNT = re.compile(
    r"€\s*(\d+(?:[.,]\d{1,2})?)\b|\b(\d+(?:[.,]\d{1,2})?)\s*(?:EUR|euro)\b",
    re.I,
)
_PAIR = re.compile(r"\b([A-Z][A-Z0-9]*)/(EUR|USD|USDT)\b", re.I)
_PLAN = re.compile(r"\b(?:plan\w*|setup\w*|concept\w*|strateg\w*)\b", re.I)
_SAVED_AMOUNT = re.compile(
    r"\b(?:opgeslagen|bewaard|vast|saved|fixed|gespeichert|fest)\b"
    r"[^.!?\n]{0,90}\b(?:strategie\w*|strategy|basisbedrag|base amount|Basisbetrag)\b"
    r"|\b(?:strategie\w*|strategy|basisbedrag|base amount|Basisbetrag)\b"
    r"[^.!?\n]{0,90}\b(?:opgeslagen|bewaard|vast|saved|fixed|gespeichert|fest)\b",
    re.I,
)


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


def append_saved_amount_provenance(
    *, message: str, answer: str, evidence: tuple[dict[str, Any], ...],
    mentioned_assets: set[str], locale: str | None,
) -> str:
    """Append one source-grounded amount fact for an amount-specific plan read.

    The user's amount is a selector, never evidence that the amount is saved.
    A second saved match leaves the relation unresolved.
    """
    amounts = {
        amount for match in _AMOUNT.finditer(message)
        if (amount := _decimal(match.group(1) or match.group(2))) is not None
    }
    pairs = {(symbol.upper(), quote.upper()) for symbol, quote in _PAIR.findall(message)}
    if len(amounts) != 1 or len(mentioned_assets) != 1 or len(pairs) > 1 or not _PLAN.search(message):
        return answer
    amount = next(iter(amounts))
    symbol = next(iter(mentioned_assets))
    named_pair = next(iter(pairs)) if pairs else None
    if named_pair and named_pair[0] != symbol:
        return answer

    setup_ids = {
        data["setup_id"] for item in evidence
        if isinstance(item, dict) and item.get("scope") == "read_active_setup"
        and item.get("status") == "completed"
        and isinstance((data := item.get("data")), dict)
        and isinstance(data.get("setup_id"), int)
        and str(data.get("symbol") or "").upper() == symbol
        and (not named_pair or str(data.get("quote_currency") or "").upper() == named_pair[1]
             or str(data.get("pair") or "").upper() == "/".join(named_pair))
    }
    matching = {
        (data["setup_id"], data["strategy_id"])
        for item in evidence
        if isinstance(item, dict) and item.get("scope") == "read_linked_strategy"
        and item.get("status") == "completed"
        and isinstance((data := item.get("data")), dict)
        and data.get("setup_id") in setup_ids
        and isinstance(data.get("strategy_id"), int)
        and str(data.get("currency") or "EUR").upper() == "EUR"
        and _decimal(data.get("base_amount")) == amount
    }
    if len(matching) != 1:
        return answer
    # The response must identify the saved amount as such, rather than merely
    # repeating a number supplied in the user's question.
    if any(
        _SAVED_AMOUNT.search(sentence)
        and any(_decimal(match.group(1) or match.group(2)) == amount
                for match in _AMOUNT.finditer(sentence))
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", answer)
    ):
        return answer
    formatted = f"{amount:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    language = (locale or "nl").lower().split("-", 1)[0]
    sentence = {
        "en": f"The linked saved strategy has a base amount of €{formatted}.",
        "de": f"Die verknüpfte gespeicherte Strategie hat einen Basisbetrag von €{formatted}.",
    }.get(language, f"De gekoppelde opgeslagen strategie heeft €{formatted} als basisbedrag.")
    return answer.rstrip() + "\n\n" + sentence
