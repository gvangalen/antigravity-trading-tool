import logging
import asyncio
from typing import Dict, Any

from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.engine.market_intelligence_engine import get_market_intelligence

logger = logging.getLogger(__name__)

class IntelligenceService:
    # 🛡️ Semaphore om te voorkomen dat er teveel 'heavy' threads tegelijk draaien
    _semaphore = asyncio.Semaphore(5)

    def __init__(self, repository: IntelligenceRepository):
        self.repository = repository

    @classmethod
    def cache_enabled(cls) -> bool:
        # Market intelligence is request/user-context sensitive. Process-local
        # caching is disabled until a Redis/shared cache with invalidation is
        # introduced.
        return False

    async def get_market_intelligence(self, user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
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

        return result
