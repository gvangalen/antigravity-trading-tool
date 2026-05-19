import json
import csv
import io
import asyncio
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.schemas.trading_schema import StrategyCreateSchema
from backend.utils.data_normalizers import (
    normalize_targets,
    normalize_number,
    normalize_string,
    normalize_array
)

logger = logging.getLogger(__name__)

# =========================================================
# SYNCHRONOUS WRAPPERS FOR LEGACY COMPONENTS
# =========================================================

def sync_generate_strategy_task(setup_id: int, user_id: int):
    from backend.celery_task.strategy_task import generate_for_setup
    task = generate_for_setup.delay(
        user_id=user_id,
        setup_id=setup_id
    )
    return task.id

def sync_analyze_strategy(strategy_id: int, user_id: int, strategy_join_row: dict):
    from backend.ai_agents.strategy_ai_agent import analyze_and_store_strategy
    return analyze_and_store_strategy(
        user_id=user_id,
        strategy_id=strategy_id,
        strategies=[strategy_join_row],
        base_strategy=strategy_join_row,
        setup=strategy_join_row,
        market_context={}
    )

class StrategyService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = StrategyRepository(db_session)

    def _format_strategy_row(self, row: dict) -> Optional[dict]:
        if not row:
            return None

        # Data JSONB unpack for permissive design
        raw_data = row.get("data")
        data = json.loads(raw_data) if isinstance(raw_data, str) else (raw_data or {})

        entry = normalize_number(row.get("entry") or data.get("entry"))
        stop_loss = normalize_number(row.get("stop_loss") or data.get("stop_loss"))
        base_amount = normalize_number(row.get("base_amount"))
        targets = normalize_targets(row.get("targets") or data.get("targets"))

        name = normalize_string(row.get("name") or data.get("name"))
        symbol = normalize_string(row.get("setup_symbol") or data.get("symbol"))
        timeframe = normalize_string(row.get("setup_timeframe") or data.get("timeframe"))
        explanation = normalize_string(row.get("explanation") or data.get("explanation"))
        risk_profile = normalize_string(row.get("risk_profile") or data.get("risk_profile"))
        entry_type = normalize_string(data.get("entry_type") or data.get("trade_execution_mode"))
        automation = normalize_string(data.get("automation"))

        tags = normalize_array(data.get("tags"))
        favorite = bool(data.get("favorite", False))

        created_at = row.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        # Decision curve serialization fixes
        decision_curve = row.get("decision_curve")
        if isinstance(decision_curve, str):
            try:
                decision_curve = json.loads(decision_curve)
            except Exception:
                decision_curve = None

        # Calculate Risk/Reward ratio for Trade setups
        risk_reward = "N/A"
        if entry and stop_loss and targets and len(targets) > 0:
            try:
                # Use the first target for the primary R:R calculation
                first_target = float(targets[0])
                risk = abs(float(entry) - float(stop_loss))
                reward = abs(first_target - float(entry))
                if risk > 0:
                    rr_ratio = round(reward / risk, 2)
                    risk_reward = f"1:{rr_ratio}"
            except (ValueError, ZeroDivisionError):
                pass

        return {
            "id": row.get("id"),
            "setup_id": row.get("setup_id"),
            "setup_name": row.get("setup_name"),

            "name": name,
            "setup_type": row.get("setup_type"),

            "execution_mode": row.get("execution_mode"),
            "base_amount": base_amount,

            "decision_curve": decision_curve,
            "decision_curve_name": data.get("decision_curve_name"),
            "decision_curve_id": row.get("decision_curve_id") or data.get("decision_curve_id"),

            "symbol": symbol,
            "timeframe": timeframe,

            "entry": entry,
            "entry_type": entry_type,
            "trade_execution_mode": entry_type,
            "targets": targets,
            "stop_loss": stop_loss,
            "risk_reward": risk_reward,

            "explanation": explanation,
            "ai_explanation": data.get("ai_explanation"),

            "risk_profile": risk_profile,
            "automation": automation,

            "tags": tags,
            "favorite": favorite,

            "created_at": created_at,
        }

    async def save_strategy(self, payload: StrategyCreateSchema, raw_data: dict, user_id: int):
        execution_mode = payload.execution_mode.lower()
        if execution_mode not in ["fixed", "custom"]:
            raise HTTPException(400, "Ongeldige execution_mode")

        if execution_mode == "custom" and not raw_data.get("decision_curve"):
            raise HTTPException(400, "decision_curve is verplicht bij custom execution")

        setup_row = await self.repository.get_setup_for_verification(payload.setup_id, user_id)
        if not setup_row:
            raise HTTPException(403, "Setup niet van gebruiker of beantwoordt niet")

        setup_type = (setup_row.get("setup_type") or "").lower()
        if setup_type not in ["dca", "trade"]:
            raise HTTPException(400, "Ongeldig setup_type")

        if setup_type == "trade":
            self._validate_trade_strategy(raw_data)

        exists = await self.repository.check_strategy_exists(payload.setup_id, user_id)
        if exists:
            raise HTTPException(409, "Strategie bestaat al voor deze setup")

        strategy_name = (payload.name or "").strip()
        if not strategy_name:
            strategy_name = f"{setup_type.upper()} {setup_row.get('symbol')} {setup_row.get('timeframe')}"

        curve_id = None
        if execution_mode == "custom":
            curve_name = raw_data.get("decision_curve_name") or f"Curve {datetime.utcnow():%Y%m%d-%H%M}"
            curve_id = await self.repository.create_indicator_curve(
                user_id, 
                json.dumps(raw_data["decision_curve"]), 
                curve_name
            )

        insert_payload = {
            "setup_id": payload.setup_id,
            "name": strategy_name,
            "setup_type": setup_type,
            "execution_mode": execution_mode,
            "base_amount": payload.base_amount
        }
        
        # Hydrate raw data with essential setup context for the JSON dump
        raw_data["setup_type"] = setup_type
        raw_data["symbol"] = setup_row.get("symbol")
        raw_data["timeframe"] = setup_row.get("timeframe")
        raw_data["setup_name"] = setup_row.get("name")

        strategy_id = await self.repository.create_strategy(insert_payload, curve_id, raw_data, user_id)
        await self.session.commit()
        
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(user_id, "strategy", self.session)
        return {"id": strategy_id, "message": "✅ Strategie opgeslagen"}

    def format_strategy_for_mobile(self, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """
        Trims and optimizes strategy payload for native mobile consumption.
        Excludes massive decision curves while keeping necessary trade/DCA configurations.
        """
        if not strategy:
            return {}

        return {
            "id": strategy.get("id"),
            "setup_id": strategy.get("setup_id"),
            "setup_name": strategy.get("setup_name"),
            "name": strategy.get("name"),
            "setup_type": strategy.get("setup_type"),
            "execution_mode": strategy.get("execution_mode"),
            "base_amount": strategy.get("base_amount"),
            "symbol": strategy.get("symbol"),
            "timeframe": strategy.get("timeframe"),
            "entry": strategy.get("entry"),
            "entry_type": strategy.get("entry_type"),
            "trade_execution_mode": strategy.get("trade_execution_mode"),
            "targets": strategy.get("targets"),
            "stop_loss": strategy.get("stop_loss"),
            "risk_reward": strategy.get("risk_reward"),
            "explanation": strategy.get("explanation"),
            "ai_explanation": strategy.get("ai_explanation"),
            "risk_profile": strategy.get("risk_profile"),
            "automation": strategy.get("automation"),
            "tags": strategy.get("tags"),
            "favorite": strategy.get("favorite"),
            "created_at": strategy.get("created_at"),
            "has_decision_curve": bool(strategy.get("decision_curve")),
            "decision_curve_name": strategy.get("decision_curve_name"),
        }

    async def query_strategies(self, user_id: int, filters: dict, format_type: Optional[str] = None) -> List[dict]:
        rows = await self.repository.query_strategies(user_id, filters)
        formatted = [self._format_strategy_row(r) for r in rows]
        if format_type == "mobile":
            return [self.format_strategy_for_mobile(s) for s in formatted if s]
        return formatted

    async def update_strategy(self, strategy_id: int, raw_data: dict, user_id: int):
        execution_mode = (raw_data.get("execution_mode") or "").lower()
        if execution_mode not in ["fixed", "custom"]:
            raise HTTPException(400, "Ongeldige execution_mode")

        if not raw_data.get("base_amount"):
            raise HTTPException(400, "base_amount is verplicht")

        if execution_mode == "custom" and not raw_data.get("decision_curve"):
            raise HTTPException(400, "decision_curve verplicht")

        existing = await self.repository.get_raw_strategy_with_setup(strategy_id, user_id)
        if not existing:
            raise HTTPException(404, "Niet gevonden")

        setup_type = (existing.get("existing_setup_type") or "").lower()
        if setup_type == "trade":
            self._validate_trade_strategy(raw_data)

        updated_count = await self.repository.update_strategy(strategy_id, user_id, raw_data, setup_type, raw_data)
        if updated_count == 0:
            raise HTTPException(403, "Update gefaald")
            
        await self.session.commit()
        return {"message": "✅ Strategie bijgewerkt"}

    async def generate_strategy_for_setup(self, setup_id: int, user_id: int) -> dict:
        task_id = await asyncio.to_thread(sync_generate_strategy_task, setup_id, user_id)
        return {"task_id": task_id}

    async def analyze_strategy(self, strategy_id: int, user_id: int) -> dict:
        row = await self.repository.get_strategy_full_join(strategy_id, user_id)
        if not row:
            raise HTTPException(404, "Strategie niet gevonden")

        result = await asyncio.to_thread(sync_analyze_strategy, strategy_id, user_id, row)

        return {
            "message": "🧠 Strategy AI analyse uitgevoerd",
            "result": result
        }

    async def delete_strategy(self, strategy_id: int, user_id: int) -> dict:
        dependents = await self.session.execute(
            text("""
                SELECT COUNT(*)
                FROM bot_configs
                WHERE strategy_id = :strategy_id AND user_id = :user_id
            """),
            {"strategy_id": strategy_id, "user_id": user_id},
        )
        if (dependents.scalar() or 0) > 0:
            raise HTTPException(409, "Strategie wordt nog gebruikt door een bot. Verwijder of wijzig eerst die bot.")

        deleted = await self.repository.delete_strategy(strategy_id, user_id)
        if deleted == 0:
            raise HTTPException(404, "Strategie niet gevonden")
        await self.session.commit()
        return {"message": "🗑 Verwijderd"}

    async def get_strategy_by_setup(self, setup_id: int, user_id: int, format_type: Optional[str] = None) -> Optional[dict]:
        row = await self.repository.get_strategy_by_setup(setup_id, user_id)
        if not row:
            return None
        formatted = self._format_strategy_row(row)
        if format_type == "mobile" and formatted:
            return self.format_strategy_for_mobile(formatted)
        return formatted

    async def get_last_strategy(self, user_id: int, format_type: Optional[str] = None) -> Optional[dict]:
        row = await self.repository.get_last_strategy(user_id)
        if not row:
            return None
        formatted = self._format_strategy_row(row)
        if format_type == "mobile" and formatted:
            return self.format_strategy_for_mobile(formatted)
        return formatted

    async def toggle_favorite(self, strategy_id: int, user_id: int) -> dict:
        new_fav = await self.repository.toggle_favorite(strategy_id, user_id)
        if new_fav is None:
            raise HTTPException(404, "Niet gevonden")
            
        await self.session.commit()
        return {"favorite": new_fav}

    async def export_strategies(self, user_id: int) -> StreamingResponse:
        rows = await self.repository.get_all_strategies_export(user_id)
        
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Symbol", "Entry", "Stop Loss", "Created"])

        for row in rows:
            data = json.loads(row["data"]) if isinstance(row.get("data"), str) else (row.get("data") or {})
            created = row["created_at"]
            writer.writerow([
                row["id"],
                data.get("symbol"),
                data.get("entry"),
                data.get("stop_loss"),
                created.strftime("%Y-%m-%d %H:%M")
            ])

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=strategies.csv"}
        )

    async def get_execution_curves(self, user_id: int) -> List[dict]:
        return await self.repository.get_execution_curves(user_id)

    async def get_active_strategy_today(self, user_id: int) -> dict:
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Europe/Amsterdam"))
        except Exception:
            now = datetime.utcnow()
        weekday = now.isoweekday()
        month_day = now.day

        rows = await self.repository.get_active_strategies_with_setup(user_id)
        
        for row in rows:
            setup_type = (row.get("setup_type") or "").lower()
            if setup_type == "trade":
                continue

            freq = (row.get("dca_frequency") or "").lower()
            try:
                day = int(row.get("dca_day")) if row.get("dca_day") is not None else None
            except (TypeError, ValueError):
                day = None
            md = row.get("dca_month_day")

            if freq == "daily" or (freq == "weekly" and day == weekday) or (freq == "monthly" and md == month_day):
                return {"active": True, "strategy": self._format_strategy_row(row)}

        return {"active": False}

    def _validate_trade_strategy(self, raw_data: dict) -> None:
        entry = normalize_number(raw_data.get("entry"))
        stop_loss = normalize_number(raw_data.get("stop_loss"))
        targets = normalize_targets(raw_data.get("targets"))

        if entry is None or stop_loss is None:
            raise HTTPException(400, "entry en stop_loss verplicht voor trade")
        if entry <= 0 or stop_loss <= 0:
            raise HTTPException(400, "entry en stop_loss moeten groter zijn dan 0")
        if stop_loss >= entry:
            raise HTTPException(400, "Voor long trades moet stop_loss lager zijn dan entry.")
        if not targets:
            raise HTTPException(400, "targets verplicht voor trade")
        invalid_targets = [target for target in targets if target is None or float(target) <= entry]
        if invalid_targets:
            raise HTTPException(400, "Voor long trades moeten alle targets hoger zijn dan entry.")

        base_amount = normalize_number(raw_data.get("base_amount"))
        if base_amount is not None and base_amount <= 0:
            raise HTTPException(400, "base_amount moet groter zijn dan 0.")
