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
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.setup_market_match_service import SetupMarketMatchService

logger = logging.getLogger(__name__)

class ScoreService:
    def __init__(self, repository: ScoreRepository, user_repository: Optional[UserRepository] = None):
        self.repository = repository
        self.user_repository = user_repository

    async def get_macro_score(self, user_id: int):
        # We invoke the legacy synchronous generation utilities via thread worker
        return await asyncio.to_thread(generate_scores_db, "macro", user_id=user_id, symbol="BTC") # Macro is asset-agnostic

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
        
        has_all_data = True
        tech_repo = None
        user_configs = []

        if refresh_if_incomplete:
            tech_repo = TechnicalDataRepository(self.repository.db)
            asset_scope = await AssetCatalogService(self.repository.db).get_asset(symbol)
            user_configs = await tech_repo.get_user_configs(
                user_id,
                symbol=symbol,
                asset_class=asset_scope.get("asset_class"),
            )

            if not user_configs:
                logger.info("No canonical indicator configuration for user=%s symbol=%s", user_id, symbol)

            for conf in user_configs:
                exists = await tech_repo.check_duplicate(conf.indicator, user_id, symbol)
                if not exists:
                    has_all_data = False
                    break

        if refresh_if_incomplete and (not scores or not has_all_data):
            logger.info(f"🚀 Data incomplete for {symbol}. Triggering RUNTIME scan...")
            try:
                from backend.utils.scoring_engine import run_category_scoring
                from backend.utils.technical_interpreter import fetch_technical_value
                
                # 1. Technical: Fetch missing values and score them individually
                user_configs = await tech_repo.get_user_configs(
                    user_id,
                    symbol=symbol,
                    asset_class=asset_scope.get("asset_class"),
                )
                tech_values = {}
                for conf in user_configs:
                    try:
                        # Haal live waarde op
                        cfg = await tech_repo.get_indicator_config(conf.indicator)
                        if cfg:
                            res = await fetch_technical_value(conf.indicator, cfg.source, cfg.link, symbol=symbol)
                            val = float(res["value"] if isinstance(res, dict) else res)
                            tech_values[conf.indicator] = val
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to fetch {conf.indicator} for {symbol}: {e}")

                # Score and Persist individual technical indicators
                tech_res = await asyncio.to_thread(
                    run_category_scoring, 
                    user_id=user_id, 
                    category="technical", 
                    indicator_values=tech_values,
                    persist=True,
                    symbol=symbol
                )

                # 2. Market (similar logic)
                mark_res = await asyncio.to_thread(generate_scores_db, "market", user_id=user_id, symbol=symbol)
                
                # 3. Macro (global)
                mac_res = await asyncio.to_thread(generate_scores_db, "macro", user_id=user_id)

                # Save daily combined scores
                await self.repository.save_daily_combined_score(
                    user_id, 
                    symbol, 
                    {
                        "macro": mac_res.get("total_score", 50),
                        "macro_interpretation": "Runtime macro scan",
                        "technical": tech_res.get("weighted_score", 50),
                        "technical_interpretation": "Runtime technical scan",
                        "market": mark_res.get("total_score", 50),
                        "market_interpretation": "Runtime market scan",
                        "setup": None
                    }
                )
                await self.repository.db.commit()
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
        )

    async def get_master_score(self, user_id: int, symbol: str = "BTC") -> MasterScoreResponse:
        from backend.domain.finn_dca_plan_contract import normalize_benchmark_weights

        assessment = await SetupMarketMatchService(self.repository.db).for_asset(user_id, symbol, setups=[])
        insight = await self.repository.get_master_score(user_id, symbol=symbol)
        
        # --- NEW: User Weights Logic ---
        user_weights = {}
        if self.user_repository:
            user = await self.user_repository.get_by_id(user_id)
            if user and user.ai_preferences:
                user_weights = user.ai_preferences.get("intelligence_weights", {})

        normalized_weights = normalize_benchmark_weights(user_weights or None)
        display_weights = {
            key.removesuffix("_score"): value
            for key, value in (normalized_weights or {}).items()
        }

        if not insight:
            return MasterScoreResponse(
                master_score=assessment["benchmark_score"],
                master_trend="–",
                master_bias="–",
                master_risk="–",
                alignment_score=0.0,
                outlook="Nog geen master-outlook",
                weights=display_weights,
                data_warnings=[] if assessment["benchmark_score"] is not None else ["De huidige benchmarkscore is niet beschikbaar."],
                domains={},
                summary="De actuele benchmark wordt uit markt-, macro- en technische scores berekend." if assessment["benchmark_score"] is not None else "Nog geen actuele benchmarkscore beschikbaar",
                date=str(assessment["as_of"]) if assessment["benchmark_score"] is not None else None
            )

        meta = insight.top_signals or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}

        # Keep the numeric master tied to the measured benchmark. Old AI
        # commentary may describe a different day and must not look current.
        final_weights = display_weights
        current_narrative = (
            assessment["benchmark_score"] is not None
            and str(insight.date) == str(assessment["as_of"])
        )
        warnings = list(meta.get("data_warnings") or [])
        if not current_narrative:
            warnings.append("AI-duiding is niet actueel en wordt niet als huidige benchmark gebruikt.")

        return MasterScoreResponse(
            master_score=assessment["benchmark_score"],
            master_trend=(insight.trend or "–") if current_narrative else "–",
            master_bias=(insight.bias or "–") if current_narrative else "–",
            master_risk=(insight.risk or "–") if current_narrative else "–",
            alignment_score=float(meta.get("alignment_score", 0)) if current_narrative else 0.0,
            outlook=meta.get("outlook", "Geen outlook") if current_narrative else "Geen actuele AI-duiding",
            weights=final_weights,
            data_warnings=warnings,
            domains=meta.get("domains", {}) if current_narrative else {},
            summary=(insight.summary or "") if current_narrative else "De actuele benchmark wordt uit markt-, macro- en technische scores berekend.",
            date=str(assessment["as_of"]) if assessment["benchmark_score"] is not None else None
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
                "macro": float(h["macro_score"] or 0),
                "technical": float(h["technical_score"] or 0),
                "market": float(h["market_score"] or 0),
                # Historical rows predate the match contract and are not
                # comparable with today's setup match. Do not relabel them.
                "setup": None,
                "btc_price": float(h["btc_price"]) if h["btc_price"] else None,
                "asset_price": float(h["asset_price"]) if "asset_price" in h and h["asset_price"] else None
            })
        return formatted
