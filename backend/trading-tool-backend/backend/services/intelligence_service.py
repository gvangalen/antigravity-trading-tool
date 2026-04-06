import logging
import asyncio
from typing import Dict, Any

from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.engine.market_intelligence_engine import get_market_intelligence

logger = logging.getLogger(__name__)

class IntelligenceService:
    def __init__(self, repository: IntelligenceRepository):
        self.repository = repository

    async def get_market_intelligence(self, user_id: int) -> Dict[str, Any]:
        daily_score = await self.repository.get_latest_daily_scores(user_id)
        
        if not daily_score:
            scores = {
                "macro": 10.0,
                "technical": 10.0,
                "market": 10.0,
                "setup": 10.0,
            }
        else:
            scores = {
                "macro": float(daily_score.macro_score or 10.0),
                "technical": float(daily_score.technical_score or 10.0),
                "market": float(daily_score.market_score or 10.0),
                "setup": float(daily_score.setup_score or 10.0),
            }

        # get_market_intelligence contains synchronous heavy data gathering 
        return await asyncio.to_thread(
            get_market_intelligence,
            user_id=user_id,
            scores=scores
        )
