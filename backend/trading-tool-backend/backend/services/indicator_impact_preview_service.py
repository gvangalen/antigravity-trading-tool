"""Read-only preview of the immediate score and bot gate after a config write.

The next numerical score needs a fresh full scoring run; never manufacture one
from a selected indicator whose source history or rule may still be missing.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from backend.services.setup_market_match_service import SetupMarketMatchService


def summarize_impact(assessment: dict, bots: list[dict]) -> dict:
    matches = [
        {
            "setup_id": row.get("setup_id"), "name": row.get("name"),
            "before_status": row.get("status"),
            "after_status": (
                "pending_score" if row.get("conditions") else "no_score_condition"
            ),
        }
        for row in assessment.get("matches") or []
    ]
    affected_bots = []
    for row in bots:
        if not row.get("is_active"):
            continue
        has_score_condition = (
            row.get("min_benchmark_score") is not None
            or row.get("max_benchmark_score") is not None
        )
        curve = row.get("decision_curve")
        if isinstance(curve, str):
            try:
                curve = json.loads(curve)
            except json.JSONDecodeError:
                curve = None
        has_score_selected_amount = (
            row.get("execution_mode") == "custom"
            and isinstance(curve, dict) and curve.get("input") == "benchmark_score"
        )
        affected_bots.append({
            "bot_id": row.get("id"), "name": row.get("name"),
            "setup_id": row.get("setup_id"), "is_live": bool(row.get("is_live")),
            "after_status": "wait_for_fresh_score" if has_score_condition or has_score_selected_amount
            else "no_score_gate_change",
        })
    return {
        "simulation_only": True,
        "before": {
            "benchmark_score": assessment.get("benchmark_score"),
            "score_status": assessment.get("source_status"),
        },
        "after": {
            "benchmark_score": None,
            "score_status": "recalculation_required",
            "reason": "source_and_rules_must_be_verified_after_save",
        },
        "setups": matches,
        "bots": affected_bots,
    }


class IndicatorImpactPreviewService:
    def __init__(self, session):
        self.session = session

    async def preview(self, *, user_id: int, symbol: str, category: str, indicator: str,
                      market_id: int | None = None) -> dict:
        symbol = str(symbol or "").strip().upper()
        category = str(category or "").strip().lower()
        indicator = str(indicator or "").strip().lower()
        if not symbol or category not in {"market", "macro", "technical"} or not indicator:
            raise ValueError("invalid_indicator_preview")
        assessment = await SetupMarketMatchService(self.session).for_asset(
            user_id, symbol, market_id=market_id)
        market_scope = "AND st.market_id = :market_id" if market_id is not None else ""
        params = {"user_id": user_id, "symbol": symbol}
        if market_id is not None:
            params["market_id"] = market_id
        result = await self.session.execute(text(f"""
            SELECT b.id, b.name, b.is_active, b.is_live,
                   st.id AS setup_id, st.min_benchmark_score, st.max_benchmark_score,
                   s.execution_mode, s.decision_curve
            FROM bot_configs b
            JOIN strategies s ON s.id = b.strategy_id AND s.user_id = b.user_id
            JOIN setups st ON st.id = s.setup_id AND st.user_id = b.user_id
            WHERE b.user_id = :user_id AND UPPER(st.symbol) = :symbol
              {market_scope}
            ORDER BY b.id
        """), params)
        return {
            "symbol": symbol, "market_id": market_id,
            "category": category, "indicator": indicator,
            **summarize_impact(assessment, [dict(row) for row in result.mappings().all()]),
        }
