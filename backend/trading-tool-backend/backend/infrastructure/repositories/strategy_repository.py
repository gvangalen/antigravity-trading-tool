import json
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from datetime import datetime

class StrategyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_setup_for_verification(self, setup_id: int, user_id: int) -> Optional[dict]:
        query = text("""
            SELECT id, name, symbol, timeframe, setup_type
            FROM setups
            WHERE id = :setup_id AND user_id = :user_id
        """)
        result = await self.session.execute(query, {"setup_id": setup_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def check_strategy_exists(self, setup_id: int, user_id: int) -> bool:
        query = text("""
            SELECT id FROM strategies
            WHERE setup_id = :setup_id AND user_id = :user_id
        """)
        result = await self.session.execute(query, {"setup_id": setup_id, "user_id": user_id})
        return result.fetchone() is not None

    async def create_indicator_curve(self, user_id: int, curve_json: str, name: str) -> int:
        query = text("""
            INSERT INTO indicator_curves (
                user_id, domain, indicator, curve, name,
                is_active, is_preset, created_at
            )
            VALUES (:user_id, 'execution', 'position_size', :curve, :name, true, false, NOW())
            RETURNING id
        """)
        result = await self.session.execute(query, {
            "user_id": user_id, 
            "curve": curve_json, 
            "name": name
        })
        row = result.fetchone()
        return row[0] if row else None

    async def create_strategy(self, payload: dict, curve_id: Optional[int], raw_data: dict, user_id: int) -> int:
        query = text("""
            INSERT INTO strategies (
                setup_id, name, setup_type,
                execution_mode, base_amount,
                decision_curve, decision_curve_id,
                entry, targets, stop_loss,
                explanation, risk_profile,
                data, created_at, user_id
            )
            VALUES (
                :setup_id, :name, :setup_type,
                :execution_mode, :base_amount,
                :decision_curve, :decision_curve_id,
                :entry, :targets, :stop_loss,
                :explanation, :risk_profile,
                :data, NOW(), :user_id
            )
            RETURNING id
        """)
        
        params = {
            "setup_id": payload["setup_id"],
            "name": payload["name"],
            "setup_type": payload["setup_type"],
            "execution_mode": payload["execution_mode"],
            "base_amount": payload["base_amount"],
            "decision_curve": json.dumps(raw_data.get("decision_curve")) if raw_data.get("decision_curve") else None,
            "decision_curve_id": curve_id,
            "entry": str(raw_data.get("entry")) if raw_data.get("entry") is not None else None,
            "targets": raw_data.get("targets"), # Assuming SQLAlchemy handles array insert if column is Array
            "stop_loss": str(raw_data.get("stop_loss")) if raw_data.get("stop_loss") is not None else None,
            "explanation": raw_data.get("explanation"),
            "risk_profile": raw_data.get("risk_profile"),
            "data": json.dumps(raw_data),
            "user_id": user_id
        }
        
        result = await self.session.execute(query, params)
        row = result.fetchone()
        return row[0] if row else None

    async def get_raw_strategy_with_setup(self, strategy_id: int, user_id: int) -> Optional[dict]:
        query = text("""
            SELECT s.*, st.symbol as setup_symbol, st.timeframe as setup_timeframe, st.setup_type as existing_setup_type
            FROM strategies s
            JOIN setups st ON st.id = s.setup_id
            WHERE s.id = :strategy_id AND s.user_id = :user_id
        """)
        result = await self.session.execute(query, {"strategy_id": strategy_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def query_strategies(self, user_id: int, filters: dict) -> List[dict]:
        q = """
            SELECT
                s.*,
                st.symbol AS setup_symbol,
                st.timeframe AS setup_timeframe,
                st.name AS setup_name
            FROM strategies s
            LEFT JOIN setups st ON st.id = s.setup_id
            WHERE s.user_id = :user_id
        """
        params = {"user_id": user_id}
        
        if filters.get("symbol"):
            q += " AND st.symbol = :symbol"
            params["symbol"] = filters["symbol"]
            
        if filters.get("timeframe"):
            q += " AND st.timeframe = :timeframe"
            params["timeframe"] = filters["timeframe"]
            
        q += " ORDER BY s.created_at DESC"
        
        result = await self.session.execute(text(q), params)
        return [dict(r._mapping) for r in result.fetchall()]

    async def update_strategy(self, strategy_id: int, user_id: int, payload: dict, existing_setup_type: str, raw_data: dict) -> int:
        query = text("""
            UPDATE strategies
            SET
                name = :name,
                setup_type = :setup_type,
                execution_mode = :execution_mode,
                base_amount = :base_amount,
                decision_curve = :decision_curve,
                decision_curve_id = :decision_curve_id,
                entry = :entry,
                targets = :targets,
                stop_loss = :stop_loss,
                explanation = :explanation,
                risk_profile = :risk_profile,
                data = :data
            WHERE id = :id AND user_id = :user_id
        """)
        
        params = {
            "name": payload.get("name"),
            "setup_type": existing_setup_type,
            "execution_mode": payload.get("execution_mode"),
            "base_amount": payload.get("base_amount"),
            "decision_curve": json.dumps(raw_data.get("decision_curve")) if raw_data.get("decision_curve") else None,
            "decision_curve_id": raw_data.get("decision_curve_id"),
            "entry": str(raw_data.get("entry")) if raw_data.get("entry") is not None else None,
            "targets": raw_data.get("targets"),
            "stop_loss": str(raw_data.get("stop_loss")) if raw_data.get("stop_loss") is not None else None,
            "explanation": raw_data.get("explanation"),
            "risk_profile": raw_data.get("risk_profile"),
            "data": json.dumps(raw_data),
            "id": strategy_id,
            "user_id": user_id
        }
        
        result = await self.session.execute(query, params)
        return result.rowcount

    async def delete_strategy(self, strategy_id: int, user_id: int) -> int:
        query = text("DELETE FROM strategies WHERE id = :id AND user_id = :user_id")
        result = await self.session.execute(query, {"id": strategy_id, "user_id": user_id})
        return result.rowcount

    async def get_strategy_by_setup(self, setup_id: int, user_id: int) -> Optional[dict]:
        # We prioritiseren de 'active_strategy_snapshot' van vandaag voor het dashboard.
        # Als die er niet is, vallen we terug op de laatst gemaakte strategie.
        query = text("""
            SELECT 
                s.id,
                s.setup_id,
                s.name,
                s.user_id,
                COALESCE(sn.entry::text, s.entry::text) as entry,
                COALESCE(sn.targets, array_to_string(s.targets, ',')) as targets,
                COALESCE(sn.stop_loss::text, s.stop_loss::text) as stop_loss,
                s.risk_profile,
                s.explanation,
                s.setup_type,
                s.execution_mode,
                s.base_amount,
                s.data,
                s.created_at
            FROM strategies s
            LEFT JOIN active_strategy_snapshot sn ON s.id = sn.strategy_id 
                AND sn.snapshot_date = CURRENT_DATE
            WHERE s.setup_id = :setup_id AND s.user_id = :user_id
            ORDER BY s.created_at DESC
            LIMIT 1
        """)
        result = await self.session.execute(query, {"setup_id": setup_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None
        
    async def get_latest_snapshot_for_setup(self, setup_id: int, user_id: int) -> Optional[dict]:
        # Directe toegang tot de snapshot (backup)
        query = text("""
            SELECT * FROM active_strategy_snapshot 
            WHERE setup_id = :setup_id AND user_id = :user_id 
            ORDER BY snapshot_date DESC LIMIT 1
        """)
        result = await self.session.execute(query, {"setup_id": setup_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def get_last_strategy(self, user_id: int) -> Optional[dict]:
        query = text("""
            SELECT *
            FROM strategies
            WHERE user_id = :user_id
            ORDER BY created_at DESC
            LIMIT 1
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None

    async def toggle_favorite(self, strategy_id: int, user_id: int) -> Optional[bool]:
        query = text("SELECT data FROM strategies WHERE id = :id AND user_id = :user_id")
        result = await self.session.execute(query, {"id": strategy_id, "user_id": user_id})
        row = result.fetchone()
        
        if not row:
            return None
            
        data = row[0] or {}
        if isinstance(data, str):
            data = json.loads(data)
            
        new_fav = not data.get("favorite", False)
        data["favorite"] = new_fav
        
        upd_query = text("UPDATE strategies SET data = :data WHERE id = :id AND user_id = :user_id")
        await self.session.execute(upd_query, {"data": json.dumps(data), "id": strategy_id, "user_id": user_id})
        return new_fav

    async def get_all_strategies_export(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT id, data, created_at
            FROM strategies
            WHERE user_id = :user_id
            ORDER BY created_at DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_execution_curves(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT id, name, curve
            FROM indicator_curves
            WHERE user_id = :user_id
              AND domain = 'execution'
              AND is_active = true
            ORDER BY created_at DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_active_strategies_with_setup(self, user_id: int) -> List[dict]:
        query = text("""
            SELECT
                s.*,
                st.dca_frequency,
                st.dca_day,
                st.dca_month_day
            FROM strategies s
            JOIN setups st ON st.id = s.setup_id
            WHERE s.user_id = :user_id
            ORDER BY s.created_at DESC
        """)
        result = await self.session.execute(query, {"user_id": user_id})
        return [dict(r._mapping) for r in result.fetchall()]

    async def get_strategy_full_join(self, strategy_id: int, user_id: int) -> Optional[dict]:
        query = text("""
            SELECT s.*, st.*
            FROM strategies s
            JOIN setups st ON st.id = s.setup_id
            WHERE s.id = :id AND s.user_id = :user_id
        """)
        result = await self.session.execute(query, {"id": strategy_id, "user_id": user_id})
        row = result.fetchone()
        return dict(row._mapping) if row else None
