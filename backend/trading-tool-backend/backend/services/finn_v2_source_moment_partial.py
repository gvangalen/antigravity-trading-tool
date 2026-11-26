"""A bounded, source-only answer when a multi-source clock claim fails.

The model's rejected wording is never reused here. Only completed reads from
the current turn can contribute account facts; ambiguous facts stay open.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from backend.services.asset_catalog_service import mentioned_catalog_symbols


_PAIR = re.compile(r"\b([A-Z][A-Z0-9]*)/(EUR|USD|USDT)\b", re.I)
_BOT_ID = re.compile(r"\bbot\s*#?\s*(\d+)\b", re.I)


def _quantity(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or number <= 0:
        return None
    return format(number.normalize(), "f").replace(".", ",")


def _score(value: Any) -> str | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not number.is_finite() or not 0 <= number <= 100:
        return None
    return format(number.normalize(), "f").replace(".", ",")


def render_source_moment_partial(
    *, question: str, evidence: tuple[dict[str, Any], ...], locale: str = "nl",
) -> str | None:
    """Recover a useful read-only answer without repeating an unverified clock."""
    language = str(locale or "nl").split("-")[0].lower()
    if language != "nl":
        return None
    assets = mentioned_catalog_symbols(question)
    pairs = {match.group(0).upper() for match in _PAIR.finditer(question)}
    if len(assets) < 2 and len(pairs) < 2:
        return None
    completed = [item for item in evidence if item.get("status") == "completed"
                 and isinstance(item.get("data"), dict)]
    if not completed:
        bot_ids = {int(match.group(1)) for match in _BOT_ID.finditer(question)}
        if len(pairs) > 1 and len(bot_ids) == 1:
            return f"Welk van de genoemde handelsparen hoort bij bot #{next(iter(bot_ids))}?"
        return "Welk asset of welke bron wil je als eerste laten controleren?"

    lines: list[str] = []
    requested_bot_ids = {int(match.group(1)) for match in _BOT_ID.finditer(question)}
    if len(requested_bot_ids) == 1:
        bot_id = next(iter(requested_bot_ids))
        status_rows = [item["data"] for item in completed
                       if item.get("scope") == "read_bot_status"
                       and item["data"].get("bot_id") == bot_id]
        if status_rows:
            status = str(status_rows[-1].get("operational_status") or "").lower()
            if status in {"active", "paused"}:
                translated = "actief" if status == "active" else "gepauzeerd"
                lines.append(f"Bot #{bot_id} heeft volgens de gelezen botstatus de status {translated}.")
        decisions = [row for item in completed if item.get("scope") == "read_review_history"
                     for row in item["data"].get("latest_bot_decisions") or []
                     if isinstance(row, dict) and row.get("bot_id") == bot_id]
        if len(decisions) == 1:
            action = str(decisions[0].get("action") or "").lower()
            if action in {"hold", "wait", "blocked"}:
                lines.append(f"De laatst gelezen beslissing voor bot #{bot_id} is wachten; dat is geen uitgevoerde koop.")

    if any(item.get("scope") == "read_latest_report" for item in completed):
        lines.append("Het dagrapport is een opgeslagen momentopname. Een score daarin is geen actuele botbeslissing.")
    if len(pairs) > 1:
        named_pairs = " en ".join(sorted(pairs))
        lines.append(f"{named_pairs} hebben afzonderlijke analyses en bronmomenten; vergelijk hun scores niet als één meting.")
    pair_scores: dict[str, str] = {}
    for item in completed:
        if item.get("scope") != "read_asset_scores":
            continue
        data = item["data"]
        pair = str(data.get("pair") or "").upper()
        score = _score(data.get("benchmark_score"))
        if pair in pairs and data.get("source_status") == "available" and score is not None:
            pair_scores[pair] = score
    for pair, score in sorted(pair_scores.items()):
        lines.append(f"De gelezen paaranalyse voor {pair} heeft benchmarkscore {score}/100.")
    if any(item.get("scope") == "read_active_setup" for item in completed):
        lines.append("Een botplan heeft eigen instapvoorwaarden; vergelijk een score alleen met de voorwaarden van het bijbehorende handelspaar.")

    position_lines: set[str] = set()
    for item in completed:
        if item.get("scope") != "read_portfolio":
            continue
        for bot in item["data"].get("bots") or []:
            if not isinstance(bot, dict) or bot.get("is_live") is not False:
                continue
            symbol = str(bot.get("symbol") or "").upper().split("/", 1)[0]
            if symbol not in assets:
                continue
            quantity = _quantity(bot.get("position_qty"))
            if quantity is None or type(bot.get("bot_id")) is not int:
                continue
            position_lines.add(f"In de gelezen Paper-portefeuille staat bij bot #{bot['bot_id']} een open positie van {quantity} {symbol}.")
    lines.extend(sorted(position_lines))

    if not lines:
        return None
    if re.search(r"\b(?:kopen|koop|buy|handelen|vervolgstap|wat\s+nu)\b", question, re.I):
        lines.append("Ik kan hiermee geen nieuwe koop onderbouwen. Controleer eerst de actuele score en de voorwaarden van het botplan voor het juiste handelspaar.")
    if len(pairs) > 1 and len(requested_bot_ids) == 1:
        lines.append(f"Welk van de genoemde handelsparen hoort bij bot #{next(iter(requested_bot_ids))}?")
    else:
        lines.append("Welk brononderdeel wil je als eerste opnieuw laten beoordelen?")
    return "\n\n".join(lines)
