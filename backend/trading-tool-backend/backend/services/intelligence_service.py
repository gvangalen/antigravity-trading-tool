import logging
import asyncio
from typing import Dict, Any

from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.engine.market_intelligence_engine import get_market_intelligence

from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class IntelligenceService:
    # 🕒 In-memory cache om 'thread exhaustion' te voorkomen
    # user_id -> { "data": dict, "expires_at": datetime }
    _cache = {}
    _CACHE_TTL_SECONDS = 30 # Kortere TTL voor live gevoel, maar lang genoeg om bursts te stoppen

    def __init__(self, repository: IntelligenceRepository):
        self.repository = repository

    async def get_market_intelligence(self, user_id: int) -> Dict[str, Any]:
        # 1. Check Cache
        now = datetime.now()
        cached = self._cache.get(user_id)
        if cached and cached["expires_at"] > now:
            # logger.info(f"🎯 Cache HIT voor Market Intelligence (user: {user_id})")
            return cached["data"]

        # 2. Fetch scores (Async)
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

        # 3. Execute heavy engine in threadpool
        # logger.info(f"⚙️ Cache MISS: Berekenen Market Intelligence in nieuwe thread (user: {user_id})")
        result = await asyncio.to_thread(
            get_market_intelligence,
            user_id=user_id,
            scores=scores
        )

        # 4. Save to Cache
        self._cache[user_id] = {
            "data": result,
            "expires_at": now + timedelta(seconds=self._CACHE_TTL_SECONDS)
        }

        return result
