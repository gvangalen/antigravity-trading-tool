"""Synchronous adapter for Celery reports and bot workers.

The arithmetic and status rules live in domain.setup_market_match. This
adapter reads the same owner-scoped daily scores, preferences and raw-source
freshness evidence as the async FINN/My Plan service.
"""

from __future__ import annotations

import json
from typing import Any

from backend.domain.finn_dca_plan_contract import benchmark_score, normalize_benchmark_weights
from backend.domain.setup_market_match import rank_matches
from backend.utils.scoring_utils import score_source_is_fresh


SETUP_COLUMNS = (
    "id", "name", "symbol", "timeframe", "setup_type",
    "min_macro_score", "max_macro_score", "min_technical_score",
    "max_technical_score", "min_market_score", "max_market_score",
)


def _fresh(conn, user_id: int, symbol: str, category: str) -> bool:
    table, name_column = {
        "macro": ("macro_data", "name"),
        "technical": ("technical_indicators", "indicator"),
        "market": ("market_data_indicators", "name"),
    }[category]
    configured = None
    with conn.cursor() as cur:
        if category == "technical":
            cur.execute(
                "SELECT indicator FROM user_indicator_configs "
                "WHERE user_id=%s AND category='technical' AND symbol=%s AND enabled=TRUE",
                (user_id, symbol),
            )
            configured = {row[0] for row in cur.fetchall()}
            if not configured:
                return False
        # Identifiers come only from the fixed map above.
        cur.execute(
            f"SELECT DISTINCT ON ({name_column}) {name_column}, source_observed_at "
            f"FROM {table} WHERE user_id=%s "
            + ("" if category == "macro" else "AND symbol=%s ")
            + f"ORDER BY {name_column}, source_observed_at DESC NULLS LAST, timestamp DESC NULLS LAST",
            (user_id,) if category == "macro" else (user_id, symbol),
        )
        rows = cur.fetchall()
    if configured is not None:
        rows = [row for row in rows if row[0] in configured]
        if {row[0] for row in rows} != configured:
            return False
    return bool(rows) and all(
        score_source_is_fresh(category, name, observed_at, symbol=symbol)
        for name, observed_at in rows
    )


def current_setup_market_assessment(conn, user_id: int, symbol: str) -> dict[str, Any]:
    symbol = str(symbol or "").strip().upper()
    with conn.cursor() as cur:
        cur.execute("SELECT ai_preferences FROM users WHERE id=%s", (user_id,))
        user_row = cur.fetchone()
        cur.execute(
            "SELECT report_date, macro_score, technical_score, market_score "
            "FROM daily_scores WHERE user_id=%s AND symbol=%s AND report_date=CURRENT_DATE LIMIT 1",
            (user_id, symbol),
        )
        daily_row = cur.fetchone()
        cur.execute(
            f"SELECT {', '.join(SETUP_COLUMNS)} FROM setups "
            "WHERE user_id=%s AND symbol=%s ORDER BY created_at DESC LIMIT 200",
            (user_id, symbol),
        )
        setups = [dict(zip(SETUP_COLUMNS, row)) for row in cur.fetchall()]

    preferences = user_row[0] if user_row else None
    if isinstance(preferences, str):
        try:
            preferences = json.loads(preferences)
        except json.JSONDecodeError:
            preferences = False
    weights = normalize_benchmark_weights(
        preferences.get("intelligence_weights") if isinstance(preferences, dict) else
        None if preferences is None else False
    ) if user_row else None
    row = dict(zip(("report_date", "macro_score", "technical_score", "market_score"), daily_row)) if daily_row else None
    scores = None
    status = "invalid_weights" if weights is None else "missing_scores"
    if weights is not None and row and all(row[f"{key}_score"] is not None for key in ("macro", "technical", "market")):
        status = "stale_sources"
        if all(_fresh(conn, user_id, symbol, key) for key in ("macro", "technical", "market")):
            scores = {key: row[f"{key}_score"] for key in ("macro", "technical", "market")}
            status = "available"
    total = benchmark_score(
        {f"{key}_score": float(value) for key, value in scores.items()}, weights,
        {f"{key}_score": True for key in scores},
    ) if scores is not None and weights is not None else None
    matches = rank_matches(setups, scores, weights)
    return {
        "symbol": symbol, "as_of": row["report_date"] if row else None,
        "source_status": status, "benchmark_score": total,
        "benchmark_weights": weights, "component_scores": scores,
        "matches": matches,
    }
