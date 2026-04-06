import json
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.repositories.agent_repository import AgentRepository
from backend.schemas.agent_schema import AgentInsightResponse, AgentReflectionResponse

class AgentService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = AgentRepository(db_session)

    async def get_insights(self, user_id: int, category: str) -> dict:
        row = await self.repository.get_insight_by_category(user_id, category)
        if not row:
            return {"insight": None}

        top = row["top_signals"]
        top_signals = json.loads(top) if isinstance(top, str) else (top or [])

        return {
            "insight": {
                "score": float(row["avg_score"]) if row["avg_score"] is not None else None,
                "trend": row["trend"],
                "bias": row["bias"],
                "risk": row["risk"],
                "summary": row["summary"],
                "top_signals": top_signals,
                "date": row["date"].isoformat() if row["date"] else None,
                "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            }
        }

    async def get_reflections(self, user_id: int, category: str) -> dict:
        rows = await self.repository.get_reflections_by_category(user_id, category)
        reflections = []
        
        for r in rows:
            reflections.append({
                "indicator": r["indicator"],
                "raw_score": float(r["raw_score"]) if r["raw_score"] is not None else None,
                "ai_score": float(r["ai_score"]) if r["ai_score"] is not None else None,
                "compliance": float(r["compliance"]) if r["compliance"] is not None else None,
                "comment": r["comment"],
                "recommendation": r["recommendation"],
                "date": r["date"].isoformat() if r["date"] else None,
                "timestamp": r["timestamp"].isoformat() if r.get("timestamp") else None,
            })
            
        return {"reflections": reflections}
