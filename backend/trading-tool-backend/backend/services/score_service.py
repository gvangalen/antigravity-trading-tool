import logging
import json
import asyncio
from typing import List, Dict, Any, Optional

from backend.utils.scoring_utils import generate_scores_db, get_scores_for_symbol
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.schemas.score_schema import (
    DailyCombinedScoreResponse, 
    MasterScoreResponse, 
    CategoryScoreResponse, 
    SetupScoreResponse, 
    ActiveSetupResponse
)

from backend.infrastructure.repositories.user_repository import UserRepository
from backend.services.setup_market_match_service import SetupMarketMatchService

logger = logging.getLogger(__name__)

class ScoreService:
    def __init__(self, repository: ScoreRepository, user_repository: Optional[UserRepository] = None):
        self.repository = repository
        self.user_repository = user_repository

    async def get_macro_score(self, user_id: int, symbol: str = "BTC"):
        return await asyncio.to_thread(generate_scores_db, "macro", user_id=user_id, symbol=symbol)

    async def get_technical_score(self, user_id: int, symbol: str = "BTC"):
        return await asyncio.to_thread(generate_scores_db, "technical", user_id=user_id, symbol=symbol)

    async def get_market_score(self, user_id: int, symbol: str = "BTC"):
        return await asyncio.to_thread(generate_scores_db, "market", user_id=user_id, symbol=symbol)

    async def get_daily_scores(
        self,
        user_id: int,
        symbol: str = "BTC",
        refresh_if_incomplete: bool = False,
    ) -> DailyCombinedScoreResponse:
        logger.info(f"🔍 Fetching daily scores for user_id={user_id} symbol={symbol}")
        scores = await self.repository.fetch_daily_scores(user_id, symbol)
        
        if refresh_if_incomplete and not scores:
            logger.info("Rebuilding canonical indicator scores for %s", symbol)
            try:
                from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
                await asyncio.to_thread(build_daily_scores_for_user, user_id, [symbol])
                scores = await self.repository.fetch_daily_scores(user_id, symbol)
            except Exception as e:
                logger.error(f"❌ Runtime scoring failed: {e}")
                scores = {}

        if not scores:
            logger.warning(f"⚠️ No daily scores found for user_id={user_id} symbol={symbol} today")
            raise LookupError(f"Geen dagelijkse scores gevonden voor {symbol}.")

        def _safe_list(val):
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return []

        assessment = await SetupMarketMatchService(self.repository.db).for_asset(user_id, symbol)
        active_setups = [ActiveSetupResponse(
            id=match["setup_id"],
            name=match["name"] or "Setup",
            symbol=match["symbol"] or symbol,
            timeframe=match["timeframe"] or "",
            setup_type=match["setup_type"],
            explanation="Berekend uit opgeslagen scorevoorwaarden en actuele benchmarkgegevens.",
            score=match["score"],
            is_active=match["is_active"],
            breakdown=match["components"],
            status=match["status"],
        ) for match in assessment["matches"]]

        def category_response(category: str) -> CategoryScoreResponse:
            status = assessment["component_source_status"][f"{category}_score"]
            if status != "fresh":
                return CategoryScoreResponse(
                    score=None,
                    interpretation="Geen actuele, onderbouwde indicatorscore beschikbaar.",
                    top_contributors=[], source_status=status,
                )
            return CategoryScoreResponse(
                score=float(scores[f"{category}_score"]),
                interpretation=scores.get(f"{category}_interpretation") or "Geen uitleg beschikbaar",
                top_contributors=_safe_list(scores.get(f"{category}_top_contributors")),
                source_status=status,
            )

        macro = category_response("macro")
        technical = category_response("technical")
        market = category_response("market")

        setup = SetupScoreResponse(
            score=next((item.score for item in active_setups if item.is_active), None),
            interpretation="Passende setups" if any(item.is_active for item in active_setups) else "Geen bewezen passende setup",
            top_contributors=[s.name for s in active_setups if s.is_active],
            active_setups=active_setups,
            source_status=assessment["source_status"],
        )

        return DailyCombinedScoreResponse(
            macro=macro,
            technical=technical,
            market=market,
            setup=setup,
            report_date=scores.get("report_date"),
            benchmark_score=assessment["benchmark_score"],
            benchmark_weights=assessment["benchmark_weights"],
            calculated_at=scores.get("calculated_at"),
            indicator_evidence=scores.get("indicator_evidence") or {},
        )

    async def get_master_score(self, user_id: int, symbol: str = "BTC") -> MasterScoreResponse:
        assessment = await SetupMarketMatchService(self.repository.db).for_asset(user_id, symbol, setups=[])
        display_weights = {
            key.removesuffix("_score"): value
            for key, value in (assessment.get("benchmark_weights") or {}).items()
        }
        available = assessment["benchmark_score"] is not None
        return MasterScoreResponse(
            master_score=assessment["benchmark_score"],
            master_trend="–", master_bias="–", master_risk="–",
            alignment_score=0.0,
            outlook="De benchmark gebruikt de actuele indicatorwegingen." if available else "Geen actuele benchmark beschikbaar",
            weights=display_weights,
            data_warnings=[] if available else ["De huidige benchmarkscore is niet beschikbaar."],
            domains={},
            summary=("De actuele benchmark wordt uit markt-, macro- en technische scores berekend."
                     if available else "Nog geen actuele benchmarkscore beschikbaar"),
            date=str(assessment["as_of"]) if available else None,
        )

    async def get_score_history(self, user_id: int, days: int = 30, symbol: str = "BTC") -> List[Dict[str, Any]]:
        """
        Retrieves historical score data for charting.
        """
        history = await self.repository.fetch_historical_scores(user_id, days, symbol=symbol)
        # Format for frontend (e.g. ensure floats, handle nulls)
        formatted = []
        for h in history:
            formatted.append({
                "date": str(h["date"]),
                "macro": float(h["macro_score"]) if h.get("macro_score") is not None else None,
                "technical": float(h["technical_score"]) if h.get("technical_score") is not None else None,
                "market": float(h["market_score"]) if h.get("market_score") is not None else None,
                # Historical rows predate the match contract and are not
                # comparable with today's setup match. Do not relabel them.
                "setup": None,
                "btc_price": float(h["btc_price"]) if h["btc_price"] else None,
                "asset_price": float(h["asset_price"]) if "asset_price" in h and h["asset_price"] else None
            })
        return formatted
