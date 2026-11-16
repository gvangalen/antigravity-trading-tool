"""Keep a correction about a named bot attached to its owner-read bot row."""

from __future__ import annotations

import re
from typing import Any


_BOT_ID = re.compile(r"\bbot\s*#?\s*(\d+)\b", re.I)
_CORRECTION = re.compile(
    r"\b(?:corrigeer|correct(?:ie|ion)?|klopt\s+niet|onjuist|fout|verkeerd|"
    r"wrong|incorrect|mistake|korrigier\w*|falsch)\b",
    re.I,
)


def focused_bot_id(message: str, previous_response: dict[str, Any] | None = None) -> int | None:
    ids = {int(match.group(1)) for match in _BOT_ID.finditer(message)}
    if len(ids) == 1:
        return next(iter(ids))
    if ids or not _CORRECTION.search(message):
        return None
    previous = previous_response or {}
    if previous.get("terminal_status") != "completed":
        return None
    prior_ids = {int(match.group(1)) for match in _BOT_ID.finditer(
        str(previous.get("user_message") or "")
    )}
    return next(iter(prior_ids)) if len(prior_ids) == 1 else None


def bot_subject_supported(
    answer: str, evidence: tuple[dict[str, Any], ...], *, bot_id: int | None,
) -> bool:
    if bot_id is None:
        return True
    rows = [row for item in evidence if item.get("scope") == "read_review_history"
            and item.get("status") == "completed" and isinstance(item.get("data"), dict)
            for row in item["data"].get("latest_bot_decisions") or [] if isinstance(row, dict)]
    if not rows:
        return True  # Other answer verifiers handle missing read evidence.
    selected = [row for row in rows if row.get("bot_id") == bot_id]
    if len(selected) != 1:
        return False
    other_ids = {int(match.group(1)) for match in _BOT_ID.finditer(answer)} - {bot_id}
    if other_ids:
        return False
    symbol = str(selected[0].get("symbol") or "").upper().split("/", 1)[0]
    target_named = bool(re.search(rf"\bbot\s*#?\s*{bot_id}\b", answer, re.I)) or bool(
        symbol and re.search(
            rf"\b{re.escape(symbol)}\b[^.!?\n]{{0,32}}\bbot\b|"
            rf"\bbot\b[^.!?\n]{{0,32}}\b{re.escape(symbol)}\b",
            answer, re.I,
        )
    )
    if not target_named:
        return False
    return target_named
