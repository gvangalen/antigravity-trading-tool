"""Resolve conversational setup references from owner-scoped, completed reads.

The model may describe a prior object, but only a completed FINN read can
establish its identity. Callers must re-read the returned ID for the owner.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


_ORDINALS = {
    "eerste": 0, "tweede": 1, "derde": 2, "vierde": 3, "vijfde": 4,
    "zesde": 5, "zevende": 6, "achtste": 7, "negende": 8, "tiende": 9,
    "first": 0, "second": 1, "third": 2, "fourth": 3, "fifth": 4,
    "sixth": 5, "seventh": 6, "eighth": 7, "ninth": 8, "tenth": 9,
    "erste": 0, "zweite": 1, "dritte": 2, "vierte": 3, "fünfte": 4,
    "sechste": 5, "siebte": 6, "achte": 7, "neunte": 8, "zehnte": 9,
}
_CARDINALS = {
    "een": 0, "twee": 1, "drie": 2, "vier": 3, "vijf": 4,
    "zes": 5, "zeven": 6, "acht": 7, "negen": 8, "tien": 9,
    "one": 0, "two": 1, "three": 2, "four": 3, "five": 4,
    "six": 5, "seven": 6, "eight": 7, "nine": 8, "ten": 9,
    "eins": 0, "zwei": 1, "drei": 2, "vier": 3, "fünf": 4,
    "sechs": 5, "sieben": 6, "acht": 7, "neun": 8, "zehn": 9,
}


def listed_setup_ordinal(message: str) -> int | None:
    """Interpret a list position, never an unanchored number as an object ID."""
    match = re.search(
        r"\b(?:(de|het|the|das|die)\s+([\wü]+)|"
        r"(nummer|nr\.?|number|no\.?|#)\s*([\wü]+)|"
        r"([1-9][0-9]?)\s*(?:e|de|ste|st|nd|rd|th))\b",
        message, re.I,
    )
    if not match:
        return None
    token = (match.group(2) or match.group(4) or match.group(5) or "").casefold()
    if token in _ORDINALS:
        return _ORDINALS[token]
    if match.group(3) and token in _CARDINALS:
        return _CARDINALS[token]
    number = re.match(r"\d+", token)
    return int(number.group()) - 1 if number else None


def verified_selected_setup(previous: Mapping[str, Any] | None) -> tuple[int, str] | None:
    """Return the last uniquely selected setup in verified read evidence."""
    if not previous or previous.get("terminal_status") not in {None, "completed"}:
        return None
    if previous.get("terminal_kind") in {
        "saved_setup_collection", "saved_confirmation_inventory", "cross_asset_rule_scope",
    }:
        return None
    subject = previous.get("verified_setup_subject") or {}
    if (
        isinstance(subject, dict)
        and isinstance(subject.get("owner_id"), int) and subject["owner_id"] > 0
        and subject.get("owner_id") == previous.get("owner_user_id")
        and isinstance(subject.get("setup_id"), int)
        and subject["setup_id"] > 0
        and isinstance(subject.get("name"), str) and subject["name"].strip()
    ):
        return subject["setup_id"], subject["name"].strip()
    visible_context = " ".join((
        str(previous.get("answer") or ""),
        str(previous.get("user_message") or ""),
    )).casefold()
    for call in reversed(previous.get("tool_trace") or []):
        if call.get("status") not in {"completed", "partial"}:
            continue
        arguments = call.get("arguments") or {}
        for item in reversed((call.get("result") or {}).get("results") or []):
            if item.get("status") != "completed":
                continue
            data = item.get("data") or {}
            if item.get("scope") == "read_active_setup":
                setup_id = data.get("setup_id")
                name = str(data.get("name") or "")
                if (isinstance(setup_id, int) and setup_id > 0 and name
                        and name.casefold() in visible_context):
                    return setup_id, name
            if item.get("scope") != "read_saved_setup_inventory":
                continue
            rows = data.get("setups") or []
            selected_ids = arguments.get("setup_ids")
            if (
                isinstance(selected_ids, list) and len(selected_ids) == 1
                and len(rows) == 1 and isinstance(rows[0], dict)
                and rows[0].get("setup_id") == selected_ids[0]
                and isinstance(selected_ids[0], int) and selected_ids[0] > 0
                and rows[0].get("name")
                and str(rows[0].get("name") or "").casefold() in visible_context
            ):
                return selected_ids[0], str(rows[0].get("name") or "")
    return None


def verified_selected_setup_asset(previous: Mapping[str, Any] | None, setup_id: int) -> str | None:
    """Return the selected setup's asset only from the same completed read."""
    subject = (previous or {}).get("verified_setup_subject") or {}
    if (
        isinstance(subject, dict)
        and isinstance(subject.get("owner_id"), int) and subject["owner_id"] > 0
        and subject.get("setup_id") == setup_id
        and subject.get("owner_id") == (previous or {}).get("owner_user_id")
    ):
        symbol = str(subject.get("symbol") or "").upper()
        if symbol:
            return symbol
    for call in reversed((previous or {}).get("tool_trace") or []):
        if call.get("status") not in {"completed", "partial"}:
            continue
        for item in reversed((call.get("result") or {}).get("results") or []):
            if item.get("status") != "completed":
                continue
            data = item.get("data") or {}
            rows = data.get("setups") if item.get("scope") == "read_saved_setup_inventory" else [data]
            for row in rows or []:
                if isinstance(row, dict) and row.get("setup_id") == setup_id:
                    symbol = str(row.get("symbol") or item.get("asset") or "").upper()
                    return symbol or None
    return None


def references_selected_setup(message: str, asset: str | None = None) -> bool:
    """Recognize a conversational pointer; identity still comes from evidence."""
    asset_prefix = rf"(?:{re.escape(asset)}[- ]?)?" if asset else ""
    return bool(
        re.search(
            r"\b(?:dit|dat|die|deze|hetzelfde|dezelfde|this|that|those|same|"
            r"diese[nrms]?|dieser|dieses)\s+" + asset_prefix
            + r"(?:plan|setup|strategie|strategy|regel|rule|niveaus?|levels?)\b",
            message, re.I,
        )
        or re.search(
            r"\b(?:daarvan|daarbij|daardoor|daarmee|daarop|daarover|"
            r"hierbij|damit|darüber)\b", message, re.I,
        )
    )
