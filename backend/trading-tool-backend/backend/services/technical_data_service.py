import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.utils.technical_interpreter import fetch_technical_value
from backend.utils.scoring_engine import score_indicator
from backend.utils.scoring_utils import normalize_indicator_name
from backend.utils.db import get_db_connection
from backend.services.onboarding_service import mark_step_completed

logger = logging.getLogger(__name__)

class TechnicalDataService:
    # 🕒 Global cache for heavy scoring ops
    _cache = {}
    _CACHE_TTL = 60

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = TechnicalDataRepository(session)

    async def add_technical_indicator(self, name_raw: str, user_id: int, symbol: str = "BTC") -> Dict[str, Any]:
        """
        Voegt een technische indicator toe, roept de interpreter op, berekent de score en slaat de waarde op.
        Ondersteunt asynchrone DB en async fetch, maar synchrone scoring via to_thread.
        """
        # Normaliseer de naam
        name = normalize_indicator_name(name_raw)

        # 1. Check op duplicates (nu symbol-aware)
        is_duplicate = await self.repository.check_duplicate(name, user_id, symbol)
        if is_duplicate:
            raise ValueError(f"Indicator '{name}' is al toegevoegd voor {symbol}.")

        # 2. Haal config op
        cfg = await self.repository.get_indicator_config(name)
        if not cfg:
            raise ValueError(f"Indicator '{name}' niet gevonden of niet actief.")

        # 3. Interpreter call (async) - Symbol doorgeven!
        result = await fetch_technical_value(
            name=name,
            source=cfg.source,
            link=cfg.link,
            symbol=symbol
        )
        if not result:
            raise ValueError(f"Geen waarde ontvangen voor '{name}' ({symbol}).")

        val = float(result["value"] if isinstance(result, dict) else result)

        # 4. Score berekenen via to_thread om de event loop niet te blokkeren
        def _score_fallback() -> Dict[str, Any]:
            conn = get_db_connection()
            if not conn:
                raise RuntimeError("Geen database verbinding voor scoring engine.")
            try:
                normalized = normalize_indicator_name(name)
                return score_indicator(
                    conn=conn,
                    category="technical",
                    indicator=normalized,
                    value=val,
                    user_id=user_id,
                )
            finally:
                conn.close()

        scored = await asyncio.to_thread(_score_fallback)

        score = scored.get("score", 10)
        advies = scored.get("trend") or "neutral"
        uitleg = scored.get("interpretation") or "Geen interpretatie beschikbaar"

        # 5. Opslaan in database via async Repository (nu symbol-aware)
        new_ind = await self.repository.add_indicator(
            name=name,
            value=val,
            score=score,
            advies=advies,
            uitleg=uitleg,
            user_id=user_id,
            symbol=symbol
        )

        # Mark onboarding step
        await mark_step_completed(user_id, "technical", self.session)

        return {
            "message": f"Indicator '{name}' toegevoegd.",
            "id": new_ind.id,
            "value": float(new_ind.value),
            "score": float(new_ind.score),
            "advies": new_ind.advies,
            "uitleg": new_ind.uitleg
        }

    async def get_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[Any]:
        return await self.repository.get_latest_for_user(user_id, symbol)

    async def get_day_indicators(self, user_id: int, symbol: Optional[str] = None) -> List[Any]:
        return await self.repository.get_day_data(user_id, symbol)

    async def delete_indicator(self, name_raw: str, user_id: int, symbol: Optional[str] = None) -> int:
        name = normalize_indicator_name(name_raw)
        return await self.repository.delete_indicator(name, user_id, symbol)

    async def get_indicator_rules(self, name_raw: str, user_id: int) -> List[Any]:
        name = normalize_indicator_name(name_raw)
        return await self.repository.get_rules_for_indicator(name, user_id)
