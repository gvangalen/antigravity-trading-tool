import logging
import asyncio
import os
import time
from copy import deepcopy
from datetime import datetime, timezone
from typing import Dict, Any

from backend.infrastructure.repositories.intelligence_repository import IntelligenceRepository
from backend.engine.market_intelligence_engine import get_market_intelligence

logger = logging.getLogger(__name__)

class IntelligenceService:
    # 🛡️ Semaphore om te voorkomen dat er teveel 'heavy' threads tegelijk draaien
    _semaphore = asyncio.Semaphore(5)
    _cache: Dict[tuple[int, str], Dict[str, Any]] = {}

    def __init__(self, repository: IntelligenceRepository):
        self.repository = repository

    @classmethod
    def cache_enabled(cls) -> bool:
        return cls.cache_ttl_seconds() > 0

    @classmethod
    def cache_ttl_seconds(cls) -> int:
        return max(0, int(os.getenv("MARKET_INTELLIGENCE_CACHE_TTL_SECONDS", "45")))

    @classmethod
    def _cache_key(cls, user_id: int, symbol: str) -> tuple[int, str]:
        return int(user_id), str(symbol or "BTC").upper()

    @classmethod
    def get_cached_result(cls, user_id: int, symbol: str) -> Dict[str, Any] | None:
        if not cls.cache_enabled():
            return None
        key = cls._cache_key(user_id, symbol)
        cached = cls._cache.get(key)
        if not cached:
            return None
        if cached["expires_at"] <= time.time():
            cls._cache.pop(key, None)
            return None
        return deepcopy(cached["payload"])

    @classmethod
    def store_cached_result(cls, user_id: int, symbol: str, payload: Dict[str, Any]) -> None:
        if not cls.cache_enabled():
            return
        key = cls._cache_key(user_id, symbol)
        cls._cache[key] = {
            "expires_at": time.time() + cls.cache_ttl_seconds(),
            "payload": deepcopy(payload),
        }

    @classmethod
    def invalidate_cached_result(cls, user_id: int, symbol: str | None = None) -> None:
        if symbol is None:
            prefix = int(user_id)
            stale_keys = [key for key in cls._cache if key[0] == prefix]
            for key in stale_keys:
                cls._cache.pop(key, None)
            return
        cls._cache.pop(cls._cache_key(user_id, symbol), None)

    async def get_market_intelligence(self, user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
        cached = self.get_cached_result(user_id, symbol)
        if cached is not None:
            return cached

        # 2. Fetch scores (Async)
        daily_score = await self.repository.get_latest_daily_scores(user_id, symbol)
        
        if not daily_score:
            return {
                "available": False,
                "data_status": "insufficient_data",
                "reason": "daily_scores_missing",
                "symbol": str(symbol or "BTC").upper(),
                "as_of": None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "daily_scores",
            }

        score_values = {
            "macro": daily_score.macro_score,
            "technical": daily_score.technical_score,
            "market": daily_score.market_score,
            "setup": daily_score.setup_score,
        }
        missing = [name for name, value in score_values.items() if value is None]
        if missing:
            return {
                "available": False,
                "data_status": "insufficient_data",
                "reason": "category_scores_missing",
                "missing_categories": missing,
                "symbol": str(symbol or "BTC").upper(),
                "as_of": daily_score.report_date.isoformat() if daily_score.report_date else None,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "source": "daily_scores",
            }

        scores = {name: float(value) for name, value in score_values.items()}

        # 3. Execute heavy engine in threadpool with Semaphore protection
        # logger.info(f"⚙️ Cache MISS: Berekenen Market Intelligence in nieuwe thread (user: {user_id})")
        async with self._semaphore:
            result = await asyncio.to_thread(
                get_market_intelligence,
                user_id=user_id,
                scores=scores
            )

        self.store_cached_result(user_id, symbol, result)
        return result
