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
    if len(mentions) != 2 or mentions[0]["symbol"] == mentions[1]["symbol"]:
        return None
    marker = re.search(r"\b(?:in\s+plaats\s+van|instead\s+of|anstatt)\b", value, re.I)
    if marker and mentions[0]["end"] <= marker.start() and mentions[1]["start"] >= marker.end():
        target, source = mentions
    elif marker and marker.end() <= mentions[0]["start"]:
        source, target = mentions
    elif re.search(r"\b(?:verwijder|haal|remove|stop)\b.*\b(?:voeg|add|volg|follow)\b", value, re.I | re.S) or re.search(
        r"\bniet\s+meer\s+volgen\b.*\b(?:volg|follow)\b", value, re.I | re.S,
    ):
        source, target = mentions
    else:
        return None
    return {"source": source, "target": target}
