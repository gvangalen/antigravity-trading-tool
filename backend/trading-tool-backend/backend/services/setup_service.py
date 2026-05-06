from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from datetime import datetime
import asyncio

from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.schemas.trading_schema import SetupCreateSchema

# =========================================================
# SYNCHRONOUS WRAPPERS FOR LEGACY COMPONENTS
# =========================================================

def sync_generate_setup_explanation(setup_id: int, user_id: int) -> str:
    from backend.ai_agents.setup_ai_agent import generate_setup_explanation
    return generate_setup_explanation(setup_id, user_id)

class SetupService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = SetupRepository(db_session)

    def _format_setup(self, item: dict) -> dict:
        if not item:
            return None
            
        created_at = item.get("created_at")
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()

        return {
            "id": item.get("id"),
            "name": item.get("name"),
            "symbol": item.get("symbol"),
            "timeframe": item.get("timeframe"),
            "setup_type": item.get("setup_type"),
            
            "dca_frequency": item.get("dca_frequency"),
            "dca_day": item.get("dca_day"),
            "dca_month_day": item.get("dca_month_day"),
            
            "account_type": item.get("account_type"),
            "min_investment": item.get("min_investment"),
            "tags": item.get("tags") or [],
            "trend": item.get("trend"),
            "score_logic": item.get("score_logic"),
            "favorite": bool(item.get("favorite")),
            "explanation": item.get("explanation"),
            "description": item.get("description"),
            "action": item.get("action"),
            "category": item.get("category"),
            
            "min_macro_score": item.get("min_macro_score"),
            "max_macro_score": item.get("max_macro_score"),
            "min_technical_score": item.get("min_technical_score"),
            "max_technical_score": item.get("max_technical_score"),
            "min_market_score": item.get("min_market_score"),
            "max_market_score": item.get("max_market_score"),
            
            "created_at": created_at,
            "user_id": item.get("user_id"),
        }

    async def save_setup(self, payload: SetupCreateSchema, raw_payload: dict, user_id: int) -> dict:
        setup_type = payload.setup_type.lower()
        if setup_type not in ["dca", "trade"]:
            raise HTTPException(400, "Ongeldig setup_type. Moet 'dca' of 'trade' zijn.")

        if setup_type == "dca" and not raw_payload.get("dca_frequency"):
            raise HTTPException(400, "dca_frequency is verplicht voor DCA setup")

        # Trade cleanup
        if setup_type == "trade":
            raw_payload["dca_frequency"] = None
            raw_payload["dca_day"] = None
            raw_payload["dca_month_day"] = None

        # Score validation
        for cat in ["macro", "technical", "market"]:
            mn = raw_payload.get(f"min_{cat}_score")
            mx = raw_payload.get(f"max_{cat}_score")
            if mn is not None and mx is not None and int(mn) > int(mx):
                raise HTTPException(400, f"min_{cat}_score mag niet hoger zijn dan max_{cat}_score")

        exists = await self.repository.check_name_exists(payload.name, user_id)
        if exists:
            raise HTTPException(409, "Setup met deze naam bestaat al")

        tags = raw_payload.get("tags", [])
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.split(",") if t.strip()]

        # Zorg dat de geparseerde velden zeker weten naar raw data overgeschreven worden
        raw_payload["name"] = payload.name
        raw_payload["setup_type"] = setup_type

        # Use the raw dict directly because of the hybrid strategy
        setup_id = await self.repository.create_setup(raw_payload, user_id, tags)
        await self.session.commit()
        
        # Async run of onboarding logic
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(user_id, "setup", self.session)

        return {"status": "success", "setup_id": setup_id}

    async def get_last_setup(self, user_id: int, setup_id: Optional[int] = None) -> dict:
        if setup_id:
            row = await self.repository.get_setup_by_id(setup_id, user_id)
        else:
            row = await self.repository.get_last_setup(user_id)
        
        return {"setup": self._format_setup(row) if row else None}

    async def get_setups(self, user_id: int, setup_type: Optional[str] = None) -> List[dict]:
        rows = await self.repository.get_all_setups(user_id, setup_type)
        return [self._format_setup(r) for r in rows]

    async def get_dca_setups(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_dca_setups(user_id)
        return [self._format_setup(r) for r in rows]

    async def get_daily_setup_scores(self, user_id: int, symbol: str = "BTC") -> List[dict]:
        # Bereken dynamisch voor het gevraagde symbool
        active_res = await self.get_active_setup(user_id, symbol)
        active = active_res.get("active")
        
        if not active:
            return []
            
        return [
            {
                "setup_id": active["setup_id"],
                "score": active["score"],
                "is_best": True,
                "name": active["name"],
                "symbol": symbol,
                "timeframe": active["timeframe"],
            }
        ]

    async def update_setup(self, setup_id: int, raw_payload: dict, user_id: int) -> dict:
        for cat in ["macro", "technical", "market"]:
            mn = raw_payload.get(f"min_{cat}_score")
            mx = raw_payload.get(f"max_{cat}_score")
            if mn is not None and mx is not None and int(mn) > int(mx):
                raise HTTPException(400, f"min_{cat}_score mag niet hoger zijn dan max_{cat}_score")

        row = await self.repository.get_setup_by_id(setup_id, user_id)
        if not row:
            raise HTTPException(403, "Geen toegang tot setup")

        updates = {}
        allowed_fields = [
            "name", "timeframe", "setup_type",
            "dca_frequency", "dca_day", "dca_month_day",
            "account_type", "min_investment", "trend", "score_logic",
            "favorite", "description", "action", "category",
            "min_macro_score", "max_macro_score",
            "min_technical_score", "max_technical_score",
            "min_market_score", "max_market_score", "explanation"
        ]

        for field in allowed_fields:
            if field in raw_payload:
                updates[field] = raw_payload[field]

        if "tags" in raw_payload:
            tags = raw_payload["tags"]
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(",") if t.strip()]
            updates["tags"] = tags

        updates["last_validated"] = datetime.utcnow()

        updated_count = await self.repository.update_setup_safe(setup_id, user_id, updates)
        if updated_count == 0:
            raise HTTPException(404, "Kon setup niet updaten")
            
        await self.session.commit()
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(user_id, "setup", self.session)
        return {"message": "Setup bijgewerkt"}

    async def delete_setup(self, setup_id: int, user_id: int) -> dict:
        deleted = await self.repository.delete_setup(setup_id, user_id)
        if deleted == 0:
            raise HTTPException(404, "Niet gevonden of geen toegang")
        await self.session.commit()
        from backend.services.onboarding_service import mark_step_completed
        await mark_step_completed(user_id, "setup", self.session)
        return {"message": "Setup verwijderd"}

    async def check_name(self, name: str, user_id: int) -> dict:
        exists = await self.repository.simple_check_name(name, user_id)
        return {"exists": exists}

    async def ai_explanation(self, setup_id: int, user_id: int) -> dict:
        explanation = await asyncio.to_thread(sync_generate_setup_explanation, setup_id, user_id)
        if not explanation:
            raise HTTPException(500, "AI uitleg kon niet worden gegenereerd")

        updated = await self.repository.update_ai_explanation(setup_id, user_id, explanation)
        if updated == 0:
            raise HTTPException(404, "Setup niet gevonden")
            
        await self.session.commit()
        return {"explanation": explanation}

    async def get_top_setups(self, user_id: int, limit: int) -> List[dict]:
        rows = await self.repository.get_top_setups(user_id, limit)
        return [self._format_setup(r) for r in rows]

    async def get_setup_by_id(self, setup_id: int, user_id: int) -> dict:
        row = await self.repository.get_setup_by_id(setup_id, user_id)
        if not row:
            raise HTTPException(404, "Setup niet gevonden")
        return self._format_setup(row)

    async def get_active_setup(self, user_id: int, symbol: str = "BTC") -> dict:
        from backend.ai_agents.setup_ai_agent import score_overlap
        from sqlalchemy import text
        
        symbol = symbol.upper()
        
        # 1. Haal huidige scores op voor deze asset
        query_scores = text("""
            SELECT macro_score, technical_score, market_score
            FROM daily_scores
            WHERE user_id = :user_id AND symbol = :symbol
            ORDER BY report_date DESC LIMIT 1
        """)
        res_scores = await self.session.execute(query_scores, {"user_id": user_id, "symbol": symbol})
        row_scores = res_scores.fetchone()
        
        macro = float(row_scores[0]) if row_scores and row_scores[0] is not None else 50.0
        technical = float(row_scores[1]) if row_scores and row_scores[1] is not None else 50.0
        market = float(row_scores[2]) if row_scores and row_scores[2] is not None else 50.0

        # 2. Haal ALLE setups op
        setups = await self.repository.get_all_setups(user_id)
        if not setups:
            return {"active": None}

        # 3. Bereken overlap score runtime
        best_setup = None
        best_score = -1

        for s in setups:
            m = score_overlap(macro, s.get("min_macro_score"), s.get("max_macro_score"))
            t = score_overlap(technical, s.get("min_technical_score"), s.get("max_technical_score"))
            mk = score_overlap(market, s.get("min_market_score"), s.get("max_market_score"))

            active_components = 0
            total_score = 0
            
            if s.get("min_macro_score") is not None or s.get("max_macro_score") is not None:
                active_components += 1
                total_score += m
            if s.get("min_technical_score") is not None or s.get("max_technical_score") is not None:
                active_components += 1
                total_score += t
            if s.get("min_market_score") is not None or s.get("max_market_score") is not None:
                active_components += 1
                total_score += mk
                
            if active_components == 0:
                raw_score = round((m + t + mk) / 3)
            else:
                raw_score = round(total_score / active_components)

            score = max(25, raw_score)

            if score > best_score:
                best_score = score
                best_setup = s

        if not best_setup:
            return {"active": None}
            
        # Return de beste
        return {
            "active": {
                "setup_id": best_setup.get("id"),
                "score": best_score,
                "ai_explanation": "Berekend via dynamische overlap.",
                "name": best_setup.get("name"),
                "symbol": symbol,
                "timeframe": best_setup.get("timeframe"),
                "trend": best_setup.get("trend"),
                "setup_type": best_setup.get("setup_type"),
                "min_investment": best_setup.get("min_investment"),
                "tags": best_setup.get("tags"),
                "favorite": best_setup.get("favorite"),
                "action": best_setup.get("action"),
                "setup_explanation": best_setup.get("explanation"),
            }
        }
