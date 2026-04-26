import logging
import json
import asyncio
from typing import Dict, Any

from backend.utils.scoring_utils import generate_scores_db, get_scores_for_symbol
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.schemas.score_schema import (
    DailyCombinedScoreResponse, 
    MasterScoreResponse, 
    CategoryScoreResponse, 
    SetupScoreResponse, 
    ActiveSetupResponse
)

logger = logging.getLogger(__name__)

class ScoreService:
    def __init__(self, repository: ScoreRepository):
        self.repository = repository

    async def get_macro_score(self, user_id: int):
        # We invoke the legacy synchronous generation utilities via thread worker
        return await asyncio.to_thread(generate_scores_db, "macro", user_id=user_id)

    async def get_technical_score(self, user_id: int):
        return await asyncio.to_thread(generate_scores_db, "technical", user_id=user_id)

    async def get_market_score(self, user_id: int):
        return await asyncio.to_thread(generate_scores_db, "market", user_id=user_id)

    async def get_daily_scores(self, user_id: int) -> DailyCombinedScoreResponse:
        logger.info(f"🔍 Fetching daily scores for user_id={user_id}")
        scores = await self.repository.fetch_daily_scores(user_id)
        logger.info(f"📊 Raw scores from DB: {scores}")
        if not scores:
            logger.warning(f"⚠️ No daily scores found for user_id={user_id} today")
            scores = {}

        def _safe_list(val):
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return []

        active_setups_raw = await self.repository.fetch_active_setups(user_id)
        
        active_setups = [
            ActiveSetupResponse(**s) for s in active_setups_raw
        ]

        macro = CategoryScoreResponse(
            score=float(scores.get("macro_score") or 0),
            interpretation=scores.get("macro_interpretation", "Geen uitleg beschikbaar"),
            top_contributors=_safe_list(scores.get("macro_top_contributors"))
        )

        technical = CategoryScoreResponse(
            score=float(scores.get("technical_score") or 0),
            interpretation=scores.get("technical_interpretation", "Geen uitleg beschikbaar"),
            top_contributors=_safe_list(scores.get("technical_top_contributors"))
        )

        market = CategoryScoreResponse(
            score=float(scores.get("market_score") or 0),
            interpretation=scores.get("market_interpretation", "Geen uitleg beschikbaar"),
            top_contributors=_safe_list(scores.get("market_top_contributors"))
        )

        setup = SetupScoreResponse(
            score=float(scores.get("setup_score") or 0),
            interpretation="Actieve setups" if active_setups else "Geen actieve setups",
            top_contributors=[s.name for s in active_setups if s.is_active],
            active_setups=active_setups
        )

        return DailyCombinedScoreResponse(
            macro=macro,
            technical=technical,
            market=market,
            setup=setup
        )

    async def get_master_score(self, user_id: int) -> MasterScoreResponse:
        insight = await self.repository.get_master_score(user_id)
        
        if not insight:
            return MasterScoreResponse(
                master_score=50.0,
                master_trend="–",
                master_bias="–",
                master_risk="–",
                alignment_score=0.0,
                outlook="Nog geen master-outlook",
                weights={},
                data_warnings=[],
                domains={},
                summary="Nog geen master score beschikbaar",
                date=None
            )

        meta = insight.top_signals or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        return MasterScoreResponse(
            master_score=float(insight.avg_score or 0),
            master_trend=insight.trend or "–",
            master_bias=insight.bias or "–",
            master_risk=insight.risk or "–",
            alignment_score=float(meta.get("alignment_score", 0)),
            outlook=meta.get("outlook", "Geen outlook"),
            weights=meta.get("weights", {}),
            data_warnings=meta.get("data_warnings", []),
            domains=meta.get("domains", {}),
            summary=insight.summary or "",
            date=str(insight.date) if insight.date else None
        )
