import logging
import asyncio
import os
from typing import Dict, Any

from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.engine.market_intelligence_engine import get_market_intelligence

from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class IntelligenceService:
    # In-memory cache is opt-in only. It is useful during bursty local use, but
    # consistency-sensitive deployments should not depend on process-local state.
    # user_id -> { "data": dict, "expires_at": datetime }
    _cache = {}
    _CACHE_TTL_SECONDS = 30
    
    # 🛡️ Semaphore om te voorkomen dat er teveel 'heavy' threads tegelijk draaien
    _semaphore = asyncio.Semaphore(5)

    def __init__(self, repository: IntelligenceRepository):
        self.repository = repository

    @classmethod
    def cache_enabled(cls) -> bool:
        return os.getenv("INTELLIGENCE_SERVICE_CACHE_ENABLED", "false").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    async def get_market_intelligence(self, user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
        now = datetime.now()
        cache_key = f"{user_id}_{symbol}"
        cache_enabled = self.cache_enabled()
        if cache_enabled:
            cached = self._cache.get(cache_key)
            if cached and cached["expires_at"] > now:
                return cached["data"]

        # 2. Fetch scores (Async)
        daily_score = await self.repository.get_latest_daily_scores(user_id, symbol)
        
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

        # 3. Execute heavy engine in threadpool with Semaphore protection
        # logger.info(f"⚙️ Cache MISS: Berekenen Market Intelligence in nieuwe thread (user: {user_id})")
        async with self._semaphore:
            result = await asyncio.to_thread(
                get_market_intelligence,
                user_id=user_id,
                scores=scores
            )

        if cache_enabled:
            self._cache[cache_key] = {
                "data": result,
                "expires_at": now + timedelta(seconds=self._CACHE_TTL_SECONDS),
            }

        return result
