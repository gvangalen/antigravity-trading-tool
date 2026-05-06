from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import json
from datetime import datetime

class SetupRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def check_name_exists(self, name: str, user_id: int) -> bool:
        query = text("""
            SELECT id FROM setups
            WHERE name = :name AND user_id = :user_id
        """)
        result = await self.session.execute(query, {"name": name, "user_id": user_id})
        return result.fetchone() is not None

    async def simple_check_name(self, name: str, user_id: int) -> bool:
        query = text("SELECT COUNT(*) FROM setups WHERE name=:name AND user_id=:user_id")
        result = await self.session.execute(query, {"name": name, "user_id": user_id})
        count = result.scalar() or 0
        return count > 0

    async def create_setup(self, payload: dict, user_id: int, tags: list) -> int:
        query = text("""
            INSERT INTO setups (
                name, timeframe,
                setup_type,
                dca_frequency, dca_day, dca_month_day,
                account_type, min_investment, tags, trend, score_logic,
                favorite, explanation, description, action, category,
                min_macro_score, max_macro_score,
                min_technical_score, max_technical_score,
                min_market_score, max_market_score,
                created_at, user_id
            )
            VALUES (
                :name, :timeframe,
                :setup_type,
                :dca_frequency, :dca_day, :dca_month_day,
                :account_type, :min_investment, :tags, :trend, :score_logic,
                :favorite, :explanation, :description, :action, :category,
                :min_macro_score, :max_macro_score,
                :min_technical_score, :max_technical_score,
                :min_market_score, :max_market_score,
                :created_at, :user_id
            )
            RETURNING id
        """)
        
        params = {
            "name": payload.get("name"),
            "timeframe": payload.get("timeframe"),
            "setup_type": payload.get("setup_type"),
            
            "dca_frequency": payload.get("dca_frequency"),
            "dca_day": payload.get("dca_day"),
            "dca_month_day": payload.get("dca_month_day"),
            
            "account_type": payload.get("account_type"),
            "min_investment": payload.get("min_investment"),
            "tags": tags,
            "trend": payload.get("trend"),
            "score_logic": payload.get("score_logic"),
            "favorite": payload.get("favorite", False),
            "explanation": payload.get("explanation"),
            "description": payload.get("description"),
            "action": payload.get("action"),
            "category": payload.get("category"),
            
            "min_macro_score": payload.get("min_macro_score"),
            "max_macro_score": payload.get("max_macro_score"),
            "min_technical_score": payload.get("min_technical_score"),
            "max_technical_score": payload.get("max_technical_score"),
            "min_market_score": payload.get("min_market_score"),
            "max_market_score": payload.get("max_market_score"),
            
            "created_at": datetime.utcnow(),
            "user_id": user_id
        }
        
        result = await self.session.execute(query, params)
        row = result.fetchone()
        return row[0] if row else None

    async def get_setup_by_id(self, setup_id: int, user_id: int) -> dict:
        query = text("SELECT * FROM setups WHERE id = :setup_id AND user_id = :user_id LIMIT 1")
        result = await self.session.execute(query, {"setup_id": setup_id, "user_id": user_id})
        return result.mappings().first()

    async def get_last_setup(self, user_id: int) -> dict:
        query = text("SELECT * FROM setups WHERE user_id = :user_id ORDER BY created_at DESC LIMIT 1")
        result = await self.session.execute(query, {"user_id": user_id})
        return result.mappings().first()

    async def get_all_setups(self, user_id: int, setup_type: str = None) -> List[dict]:
        q = "SELECT * FROM setups WHERE user_id = :user_id"
        params = {"user_id": user_id}
        
        if setup_type:
            q += " AND LOWER(setup_type) = LOWER(:setup_type)"
            params["setup_type"] = setup_type
            
        q += " ORDER BY created_at DESC LIMIT 200"
        
        query = text(q)
        result = await self.session.execute(query, params)
        return result.mappings().all()

    async def get_user_setups(self, user_id: int) -> List[dict]:
        """Alias for compatibility with context builders"""
        return await self.get_all_setups(user_id)

    async def get_dca_setups(self, user_id: int) -> List[dict]:
        query = text("SELECT * FROM setups WHERE setup_type = 'dca' AND user_id = :user_id ORDER BY created_at DESC")
        result = await self.session.execute(query, {"user_id": user_id})
        return result.mappings().all()

    async def get_daily_scores(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT ds.setup_id, ds.score, ds.is_best, 
                   s.name, s.symbol, s.timeframe
            FROM daily_setup_scores ds
            JOIN setups s ON s.id = ds.setup_id
            WHERE ds.user_id = :user_id AND ds.report_date = CURRENT_DATE
            ORDER BY ds.score DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return result.mappings().all()

    async def get_active_setup(self, user_id: int) -> dict:
        query = text("""
            SELECT ds.setup_id, ds.score, ds.explanation as ai_explanation,
                   s.name, s.symbol, s.timeframe, s.trend, s.setup_type,
                   s.min_investment, s.tags, s.favorite, s.action, s.explanation as setup_explanation
            FROM daily_setup_scores ds
            JOIN setups s ON s.id = ds.setup_id
            WHERE ds.report_date = CURRENT_DATE
              AND ds.user_id = :user_id
              AND ds.is_best = TRUE
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return result.mappings().first()

    async def get_top_setups(self, user_id: int, limit: int) -> List[dict]:
        query = text("SELECT * FROM setups WHERE user_id = :user_id ORDER BY created_at DESC LIMIT :limit")
        result = await self.session.execute(query, {"user_id": user_id, "limit": limit})
        return result.mappings().all()

    async def update_setup(self, setup_id: int, user_id: int, update_fields: str, values: list):
        query_str = f"UPDATE setups SET {update_fields} WHERE id = :_id AND user_id = :_uid"
        
        # We manually build parameters for SQLAlchemy from the list
        # We rely on the caller sending a safely constructed raw sql string 
        # Actually since we want pure clean logic, let's pass a dict.
        pass

    async def update_setup_safe(self, setup_id: int, user_id: int, updates: dict):
        if not updates:
            return 0
            
        set_clauses = []
        for key in updates.keys():
            set_clauses.append(f"{key} = :{key}")
            
        query_str = f"UPDATE setups SET {', '.join(set_clauses)} WHERE id = :_id AND user_id = :_uid"
        
        params = updates.copy()
        params["_id"] = setup_id
        params["_uid"] = user_id
        
        query = text(query_str)
        result = await self.session.execute(query, params)
        return result.rowcount

    async def delete_setup(self, setup_id: int, user_id: int) -> int:
        query = text("DELETE FROM setups WHERE id = :id AND user_id = :user_id")
        result = await self.session.execute(query, {"id": setup_id, "user_id": user_id})
        return result.rowcount

    async def update_ai_explanation(self, setup_id: int, user_id: int, explanation: str) -> int:
        query = text("""
            UPDATE setups
            SET explanation = :explanation, last_validated = NOW()
            WHERE id = :id AND user_id = :user_id
        """)
        result = await self.session.execute(query, {"explanation": explanation, "id": setup_id, "user_id": user_id})
        return result.rowcount
