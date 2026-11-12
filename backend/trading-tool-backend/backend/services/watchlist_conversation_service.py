"""Catalog-backed asset mentions for the guided watchlist chat flow."""
from __future__ import annotations

import re
from typing import Any, Mapping


def asset_mentions(text: str, catalog: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return ordered, non-overlapping explicit asset mentions, without guessing.

    Names and aliases come from the asset catalog. A quoted pair is retained so
    the caller can distinguish a user's exact choice from a bare base asset.
    """
    text = str(text or "")
    candidates: list[dict[str, Any]] = []
    for symbol, asset in catalog.items():
        if asset.get("is_active") is False:
            continue
        symbol = str(symbol).upper()
        names = {symbol, str(asset.get("display_name") or ""), *(str(alias) for alias in asset.get("aliases") or ())}
        for name in names:
            if not name.strip():
                continue
            pattern = rf"(?<![\w]){re.escape(name.strip())}(?![\w])"
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                quote = None
                pair = re.match(r"\s*[/\-]\s*([A-Za-z0-9]{2,12})\b", text[match.end():])
                if pair and str(asset.get("asset_class") or "").lower() == "crypto":
                    quote = pair.group(1).upper()
                candidates.append({
                    "symbol": symbol,
                    "asset_class": str(asset.get("asset_class") or "unknown").lower(),
                    "display_name": str(asset.get("display_name") or symbol),
                    "start": match.start(),
                    "end": match.end() + (pair.end() if quote else 0),
                    "quote_currency": quote,
                })
    candidates.sort(key=lambda item: (item["start"], -(item["end"] - item["start"]), item["symbol"]))
    result: list[dict[str, Any]] = []
    for item in candidates:
        if any(item["start"] < previous["end"] and item["end"] > previous["start"] for previous in result):
            continue
        result.append(item)
    return result


def replacement_mentions(text: str, catalog: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, Any]] | None:
    """Resolve only an explicitly directed two-asset replacement.

    This extracts user-supplied facts; it does not choose an operation or
    authorize a write. Unknown and ambiguous asset lists remain unresolved.
    """
    value = str(text or "")
    mentions = asset_mentions(value, catalog)
    if len({mention["symbol"] for mention in mentions}) != 2:
        return None

    def direction(fragment: str, pair: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | None:
        first, second = pair
        marker = re.search(r"\b(?:in\s+plaats\s+van|instead\s+of|anstatt)\b", fragment, re.I)
        if marker and first["end"] <= marker.start() and second["start"] >= marker.end():
            return second, first
        if marker and marker.end() <= first["start"]:
            return first, second
        if re.search(r"\b(?:vervang|replace|ersetze)\b.*\b(?:door|with|durch)\b", fragment, re.I | re.S):
            if re.search(r"\b(?:niet|not|nicht)\b", fragment, re.I):
                return None
            return first, second
        if re.search(r"\b(?:verwijder|haal|remove|stop)\b.*\b(?:voeg|add|volg|follow)\b", fragment, re.I | re.S) or re.search(
            r"\bniet\s+meer\s+volgen\b.*\b(?:volg|follow)\b", fragment, re.I | re.S,
        ):
            return first, second
        return None

    directions: list[tuple[dict[str, Any], dict[str, Any]]] = []
    extra_command = False
    for sentence in re.finditer(r"[^.;!?]+", value):
        for clause in re.split(r"(?=\b(?:vervang|replace|ersetze)\b)", sentence.group(), flags=re.I):
            clause_mentions = asset_mentions(clause, catalog)
            # More than two mentions in one clause can describe a second or
            # self-directed replacement. Never discard those instructions.
            if len(clause_mentions) > 2:
                return None
            if len(clause_mentions) == 2 and re.search(r"\b(?:vervang|replace|ersetze)\b", clause, re.I) and re.search(
                r"\b(?:niet|not|nicht)\b", clause, re.I,
            ):
                return None
            distinct = list(dict.fromkeys(item["symbol"] for item in clause_mentions))
            if len(clause_mentions) == 2 and len(distinct) == 1 and re.search(
                r"\b(?:vervang|replace|ersetze)\b", clause, re.I,
            ):
                return None
            if len(distinct) == 2:
                pair = [next(item for item in clause_mentions if item["symbol"] == symbol) for symbol in distinct]
                parsed = direction(clause, pair)
                if parsed:
                    directions.append(parsed)
                elif re.search(r"\b(?:vervang|replace|ersetze|verwijder|haal|remove|stop|voeg|add|volg|follow)\b", clause, re.I):
                    extra_command = True
            elif len(clause_mentions) == 1 and re.search(
                r"\b(?:vervang|replace|ersetze|verwijder|haal|remove|stop|voeg|add|volg|follow)\b",
                clause, re.I,
            ):
                extra_command = True
    has_directed_clause = bool(directions)
    if not directions:
        if len(mentions) != 2:
            return None
        parsed = direction(value, mentions)
        if parsed:
            directions.append(parsed)
    if not directions or (has_directed_clause and extra_command):
        return None
    source, target = directions[0]
    for other_source, other_target in directions[1:]:
        if (source["symbol"], target["symbol"]) != (other_source["symbol"], other_target["symbol"]):
            return None
        for current, other in ((source, other_source), (target, other_target)):
            quote = other["quote_currency"]
            if quote:
                if current["quote_currency"] and current["quote_currency"] != quote:
                    return None
                current["quote_currency"] = quote
    return {"source": source, "target": target}


def ambiguous_asset_change_scope(text: str, catalog: Mapping[str, Mapping[str, Any]]) -> bool:
    """A change to an asset with no named product surface needs clarification.

    The asset itself is resolved from the catalog. We only recognize the
    ambiguous shape of the request; we do not infer a watchlist or portfolio
    mutation from it.
    """
    value = str(text or "")
    if len(asset_mentions(value, catalog)) != 1:
        return False
    if re.search(r"\b(?:watchlist|wachtlist|wachtlijst|volglijst|portfolio|portefeuille|bot|strategie|strategy|setup)\b", value, re.I):
        return False
    if re.search(r"\b(?:volg|volgen|follow|following|voeg|toevoegen|add|verwijder|remove)\b", value, re.I):
        return False
    return bool(
        re.search(r"\b(?:aandeel|share|stock|asset|anteil|aktie)\b", value, re.I)
        and re.search(r"\b(?:aanpass\w*|wijzig\w*|verander\w*|omzet\w*|change|switch|convert|adjust|änder\w*|wechsel\w*)\b", value, re.I)
    )


def asks_for_watchlist_inventory(text: str) -> bool:
    """Identify an explicit request to list saved watchlist entries."""
    value = str(text or "")
    if not re.search(r"\b(?:watchlist|wachtlist|wachtlijst|volglijst|marktenlijst)\b", value, re.I):
        return False
    if re.search(r"\b(?:voeg|toevoegen|add|verwijder|remove|vervang|replace|koop|buy|sell|verkoop)\b", value, re.I):
        return False
    return bool(
        re.search(r"\b(?:toon|laat\s+(?:me\s+)?zien|geef\s+(?:me\s+)?een\s+overzicht|show|list|zeige|auflisten)\b", value, re.I)
        or re.search(r"\b(?:welke|wat|which|what|welche|was)\b.*\b(?:staan|staat|op|in|are|is|on|stehen|steht|sind)\b", value, re.I)
    )
