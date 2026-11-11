"""Owner-scoped, non-executable FINN manual trade plan persistence."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text

from backend.domain.finn_manual_trade_plan_contract import validate_manual_trade_plan


async def verified_plan_market(session: Any, plan: dict[str, Any]) -> int | None:
    """Require an active exact crypto pair; stocks use their catalog listing."""
    validated = validate_manual_trade_plan(plan)
    if validated["asset_class"] != "crypto":
        return None
    result = await session.execute(text(
        "SELECT id FROM trading_markets WHERE asset_symbol=:asset "
        "AND quote_currency=:quote AND venue=:venue AND is_active=TRUE LIMIT 1"
    ), {
        "asset": validated["asset"], "quote": validated["quote_currency"],
        "venue": validated["venue"],
    })
    market_id = result.scalar_one_or_none()
    if market_id is None:
        raise ValueError("manual_trade_exact_market_unavailable")
    return int(market_id)


async def save_manual_trade_plan(
    session: Any, *, user_id: int, source_run_id: str, fields: dict[str, Any],
) -> dict[str, Any]:
    plan = validate_manual_trade_plan(fields)
    if plan["level_source"] == "market_derived":
        from backend.services.finn_manual_trade_suggestion_service import verify_suggested_manual_trade_plan

        await verify_suggested_manual_trade_plan(session, plan, user_id=user_id)
    market_id = await verified_plan_market(session, plan)
    stored = {**plan, "market_id": market_id}
    proposed_id = f"finn-manual-trade-plan-{uuid.uuid4().hex}"
    inserted = await session.execute(text(
        "INSERT INTO finn_manual_trade_plans (id,user_id,source_run_id,plan_json) "
        "VALUES (:id,:user_id,:run_id,CAST(:plan_json AS jsonb)) "
        "ON CONFLICT (user_id,source_run_id) DO NOTHING RETURNING id"
    ), {
        "id": proposed_id, "user_id": user_id, "run_id": source_run_id,
        "plan_json": json.dumps(stored, sort_keys=True),
    })
    plan_id = inserted.scalar_one_or_none()
    if plan_id is None:
        existing = await session.execute(text(
            "SELECT id,plan_json FROM finn_manual_trade_plans "
            "WHERE user_id=:user_id AND source_run_id=:run_id"
        ), {"user_id": user_id, "run_id": source_run_id})
        row = existing.mappings().one()
        if dict(row["plan_json"] or {}) != stored:
            raise ValueError("manual_trade_plan_run_conflict")
        plan_id = row["id"]
    return {"ok": True, "id": plan_id, "asset": plan["asset"],
            "quote_currency": plan["quote_currency"], "executable": False,
            "operation": "create_manual_trade_plan"}
