import logging
import asyncio
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from backend.infrastructure.repositories.dashboard_repository import DashboardRepository
from backend.schemas.dashboard_schema import DashboardResponse

logger = logging.getLogger(__name__)

# =========================================================
# SYNCHRONOUS WRAPPER FOR SCORING ENGINE
# =========================================================
def sync_get_scores_for_symbol(user_id: int) -> dict:
    from backend.utils.scoring_utils import get_scores_for_symbol
    try:
        return get_scores_for_symbol(user_id=user_id, include_metadata=True)
    except TypeError:
        return get_scores_for_symbol(include_metadata=True)

class DashboardService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = DashboardRepository(db_session)

    async def get_dashboard_data(self, user_id: int) -> DashboardResponse:
        try:
            # Parallel Database Queries
            market_data_task = self.repository.get_latest_market_data(user_id)
            technical_data_task = self.repository.get_latest_technical_data(user_id)
            macro_data_task = self.repository.get_latest_macro_data(user_id)
            setups_task = self.repository.get_user_setups_summary(user_id)
            
            market_data, technical_rows, macro_data, setups = await asyncio.gather(
                market_data_task,
                technical_data_task,
                macro_data_task,
                setups_task
            )
            
            # Formatting Technical Data
            technical_data = {
                row["indicator"]: {
                    "value": row["value"],
                    "score": row["score"],
                    "timestamp": row["timestamp"],
                }
                for row in technical_rows
            }
            
            # Execute Sync Scoring Request
            scores = await asyncio.to_thread(sync_get_scores_for_symbol, user_id)
            
            macro_score = scores.get("macro_score", 0)
            technical_score = scores.get("technical_score", 0)
            market_score = scores.get("market_score", 0)
            setup_score = scores.get("setup_score", 0)
            
            # Logic & Explanations formatting
            macro_explanation = (
                "📊 Gebaseerd op: " + ", ".join(d["name"] for d in macro_data)
                if macro_data else "❌ Geen macrodata"
            )

            if technical_data:
                technical_explanation = " | ".join(
                    f"{k.upper()}: {v['value']} (score {v['score']})"
                    for k, v in technical_data.items()
                )
            else:
                technical_explanation = "❌ Geen technische data"

            setup_explanation = (
                f"🧠 {len(setups)} actieve setups" if setups else "❌ Geen setups"
            )
            
            return DashboardResponse(
                user_id=user_id,
                market_data=market_data,
                technical_data=technical_data,
                macro_data=macro_data,
                setups=setups,
                scores={
                    "macro": macro_score,
                    "technical": technical_score,
                    "market": market_score,
                    "setup": setup_score
                },
                explanation={
                    "macro": macro_explanation,
                    "technical": technical_explanation,
                    "setup": setup_explanation
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Dashboard data aggregatie faalde: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Dashboard data ophalen mislukt.")
            
    async def get_trading_advice(self, symbol: str, user_id: int) -> dict:
        row = await self.repository.get_latest_trading_advice(user_id, symbol)
        if not row:
            raise HTTPException(status_code=404, detail=f"Geen advies voor {symbol}.")
        
        if row.get("timestamp") and hasattr(row["timestamp"], "isoformat"):
            row["timestamp"] = row["timestamp"].isoformat()
            
        return row

    async def get_top_setups(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_top_setups(user_id)
        for row in rows:
            if row.get("timestamp") and hasattr(row["timestamp"], "isoformat"):
                row["timestamp"] = row["timestamp"].isoformat()
        return rows

    async def get_setup_summary(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_user_setups_summary(user_id)
        return [
            {"name": row["name"], "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else row["timestamp"]}
            for row in rows
        ]

    async def check_health(self) -> dict:
        is_healthy = await self.repository.check_health()
        if not is_healthy:
            raise HTTPException(status_code=500, detail="HEALTH01: DB-connectie faalt.")
        return {"status": "ok"}
