"""Fail-closed server-side rollout for FINN closed-trade reviews.

Default is off. `allowlist` requires explicit positive user IDs, while `all`
is a separate deliberate product rollout. A malformed value never enables a
user. This gate controls API, FINN coach reads and both scheduled jobs.
"""

import os

from fastapi import HTTPException


def allowed_trade_review_users() -> set[int] | None:
    mode = os.getenv("FINN_TRADE_REVIEW_ROLLOUT", "off").strip().lower()
    if mode == "all":
        return None
    if mode != "allowlist":
        return set()
    raw = os.getenv("FINN_TRADE_REVIEW_USER_IDS", "")
    parts = [part.strip() for part in raw.split(",")]
    if not parts or len(parts) > 100 or any(
        not part.isascii() or not part.isdigit() or len(part) > 10
        or not 1 <= int(part) <= 2_147_483_647 for part in parts
    ):
        return set()
    return {int(part) for part in parts}


def trade_review_enabled(user_id: int) -> bool:
    allowed = allowed_trade_review_users()
    return allowed is None or int(user_id) in allowed


def require_trade_review_access(user_id: int) -> None:
    if not trade_review_enabled(user_id):
        raise HTTPException(404, "FINN trade-review is niet beschikbaar")
