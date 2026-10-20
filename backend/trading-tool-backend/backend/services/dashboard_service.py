import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from backend.infrastructure.repositories.dashboard_repository import DashboardRepository
from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.platform_metrics import record_latency_sample
from backend.services.locale_service import localize_finn_payload
from backend.schemas.dashboard_schema import (
    DashboardResponse, MobileOverviewResponse, MobilePortfolioOverviewSchema,
    MobileAssetWatchlistSchema, MobileActiveBotSchema, MobileFinnBriefingSchema,
    MobileIntelligenceEventSchema
)

logger = logging.getLogger(__name__)


def _safe_event_attr(event: Any, key: str, default: Any = None) -> Any:
    if isinstance(event, dict):
        return event.get(key, default)
    data = getattr(event, "__dict__", {}) or {}
    return data.get(key, default)


def _asset_logo_url(symbol: str) -> str | None:
    normalized = str(symbol or "").strip().upper()
    if not normalized:
        return None
    return f"https://assets.coincap.io/assets/icons/{normalized.lower()}@2x.png"

class DashboardService:
    def __init__(self, db_session: AsyncSession):
        self.session = db_session
        self.repository = DashboardRepository(db_session)

    @classmethod
    def mobile_overview_cache_enabled(cls) -> bool:
        # Multi-instance safety: mobile/dashboard state is write-sensitive and
        # must not be served from process-local memory. Re-enable this only via
        # a shared cache with explicit invalidation.
        return False

    @classmethod
    def invalidate_cache(cls, user_id: int):
        logger.debug(
            "Mobile overview cache invalidation skipped for user_id=%s; process-local cache is disabled.",
            user_id,
        )

    async def get_dashboard_data(self, user_id: int, symbol: str = "BTC") -> DashboardResponse:
        started = time.perf_counter()
        try:
            # A single AsyncSession backs this service. Keep DB work sequential
            # so one request cannot concurrently drive multiple awaits through
            # the same transaction/session state.
            market_data = await self.repository.get_latest_market_data(user_id, symbol)
            technical_rows = await self.repository.get_latest_technical_data(user_id, symbol)
            macro_data = await self.repository.get_latest_macro_data(user_id)
            setups = await self.repository.get_user_setups_summary(user_id)
            
            # Formatting Technical Data
            technical_data = {
                row["indicator"]: {
                    "value": row["value"],
                    "score": row["score"],
                    "timestamp": row["timestamp"],
                }
                for row in technical_rows
            }
            
            from backend.services.setup_market_match_service import SetupMarketMatchService
            score_assessment = await SetupMarketMatchService(self.session).for_asset(
                user_id, symbol, setups=[],
            )
            # The dashboard, Analyse and FINN read the same Score 2.0
            # projection. A raw historical score must not revive a component
            # whose source is now stale or incomplete.
            reported_scores = score_assessment["reported_scores"]
            macro_score = reported_scores.get("macro_score")
            technical_score = reported_scores.get("technical_score")
            market_score = reported_scores.get("market_score")
            
            # GET DYNAMIC SETUP SCORE
            from backend.services.setup_service import SetupService
            setup_service = SetupService(self.session)
            active_setup_dict = await setup_service.get_active_setup(user_id, symbol)
            active_setup = active_setup_dict.get("active")
            setup_score = active_setup.get("score") if active_setup else None
            
            # Logic & Explanations formatting
            macro_explanation = (
                "📊 Gebaseerd op: " + ", ".join(d["name"] for d in macro_data)
                if macro_data else "❌ Geen macrodata"
            )

            if technical_data:
                technical_explanation = " | ".join(
                    f"{k.upper()}: {v['value']} (score {v['score']})"
                    for k, v in technical_data.items()
                )
            else:
                technical_explanation = "❌ Geen technische data"

            setup_explanation = (
                f"🧠 {len(setups)} actieve setups" if setups else "❌ Geen setups"
            )
            
            return DashboardResponse(
                user_id=user_id,
                market_data=market_data,
                technical_data=technical_data,
                macro_data=macro_data,
                setups=setups,
                scores={
                    "macro": macro_score,
                    "technical": technical_score,
                    "market": market_score,
                    "setup": setup_score
                },
                explanation={
                    "macro": macro_explanation,
                    "technical": technical_explanation,
                    "setup": setup_explanation
                }
            )
            
        except Exception as e:
            logger.error(f"❌ Dashboard data aggregatie faalde: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Dashboard data ophalen mislukt.")
        finally:
            record_latency_sample(
                "dashboard_aggregation_latency_ms",
                (time.perf_counter() - started) * 1000,
            )
            
    async def get_trading_advice(self, symbol: str, user_id: int) -> dict:
        row = await self.repository.get_latest_trading_advice(user_id, symbol)
        if not row:
            raise HTTPException(status_code=404, detail=f"Geen advies voor {symbol}.")
        
        if row.get("timestamp") and hasattr(row["timestamp"], "isoformat"):
            row["timestamp"] = row["timestamp"].isoformat()
            
        return row

    async def get_top_setups(self, user_id: int) -> List[dict]:
        from backend.services.setup_market_match_service import SetupMarketMatchService

        assessment = await SetupMarketMatchService(self.session).for_all_assets(user_id)
        return [{"name": match["name"], "symbol": match["symbol"],
                 "timeframe": match["timeframe"], "score": match["score"],
                 "status": match["status"],
                 "explanation": "; ".join(match["reasons"]), "timestamp": None}
                for match in assessment["matches"][:5]]

    async def get_setup_summary(self, user_id: int) -> List[dict]:
        rows = await self.repository.get_user_setups_summary(user_id)
        return [
            {"name": row["name"], "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else row["timestamp"]}
            for row in rows
        ]

    async def check_health(self) -> dict:
        is_healthy = await self.repository.check_health()
        if not is_healthy:
            raise HTTPException(status_code=500, detail="HEALTH01: DB-connectie faalt.")
        return {"status": "ok"}

    async def get_mobile_overview(
        self,
        user_id: int,
        symbol: str | None = None,
        bypass_cache: bool = False,
        locale: str = "nl",
    ) -> MobileOverviewResponse:
        logger.info(f"🔄 [MobileOverview] Executing hardened composition for user_id={user_id}.")

        # 2. Setup symbols and default fallback structs
        normalized_symbol = str(symbol or "").strip().upper()
        if normalized_symbol:
            symbols = [normalized_symbol]
        else:
            # Fetch real watchlist for user from database
            query = text("SELECT symbol FROM watchlists WHERE user_id = :user_id")
            result = await self.session.execute(query, {"user_id": user_id})
            symbols = [row.symbol.upper() for row in result.fetchall()]
            if not symbols:
                symbols = ["BTC", "ETH", "SOL"]
            
        # We declare safe defaults for all sub-components so they are populated even under failure
        prices_data = {s: {"price": None, "change_24h": None} for s in symbols}
        bot_portfolios = []
        asset_catalog_map = {}

        # 3. Run DB-backed components sequentially. A single AsyncSession must
        # not be shared across concurrent DB awaits.
        try:
            prices_data = await self.repository.get_latest_prices_and_changes(user_id, symbols) or prices_data
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P1 Error: prices failed: {e}", exc_info=True)

        try:
            asset_catalog_map = await AssetCatalogService(self.session).get_assets(symbols)
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P1b Error: asset catalog failed: {e}", exc_info=True)

        try:
            from backend.services.bot_service import BotService
            bot_service = BotService(self.session)
            bot_portfolios = await bot_service.get_bot_portfolios(user_id) or []
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P2 Error: bot portfolios failed: {e}", exc_info=True)

        # Navigation and overview GETs are read-only. Coach updates are
        # produced from saved events and read from /assistant/feed instead.

        # 5. PRIORITEIT 1: Process watchlist scores dynamically via standard score engine
        from backend.services.intelligence_semantics import get_macro_semantics, get_technical_semantics, get_market_semantics
        from backend.services.setup_market_match_service import SetupMarketMatchService
        from backend.infrastructure.repositories.setup_repository import SetupRepository

        watchlist_items = []
        match_service = SetupMarketMatchService(self.session)
        owned_setups = await SetupRepository(self.session).get_all_setups(user_id)
        for sym in symbols:
            price_info = prices_data.get(sym, {}) if isinstance(prices_data, dict) else {}
            assessment = await match_service.for_asset(user_id, sym, setups=owned_setups)
            reported_scores = assessment["reported_scores"]
            macro_val = (float(reported_scores["macro_score"])
                         if reported_scores["macro_score"] is not None else None)
            tech_val = (float(reported_scores["technical_score"])
                        if reported_scores["technical_score"] is not None else None)
            mkt_val = (float(reported_scores["market_score"])
                       if reported_scores["market_score"] is not None else None)
            ranked_match = assessment["matches"][0] if assessment["matches"] else None
            setup_match_score = ranked_match["score"] if ranked_match else None
            setup_match_status = ranked_match["status"] if ranked_match else (
                "no_setups" if not assessment["matches"] else assessment["source_status"]
            )

            macro_sem = get_macro_semantics(macro_val) if macro_val is not None else {"regime": "Niet beschikbaar", "risk_state": "Onbekend"}
            tech_sem = get_technical_semantics(tech_val) if tech_val is not None else {"structure": "Niet beschikbaar"}
            mkt_sem = get_market_semantics(mkt_val) if mkt_val is not None else {"posture": "Niet beschikbaar"}
            asset_meta = asset_catalog_map.get(sym, {})

            watchlist_items.append(MobileAssetWatchlistSchema(
                symbol=sym,
                display_name=asset_meta.get("display_name") or sym,
                asset_class=asset_meta.get("asset_class"),
                logo_url=asset_meta.get("logo_url") or _asset_logo_url(sym),
                price=price_info.get("price"),
                change_24h=price_info.get("change_24h"),
                macro_score=macro_val,
                technical_score=tech_val,
                market_score=mkt_val,
                setup_score=setup_match_score,
                setup_match_score=setup_match_score,
                setup_match_status=setup_match_status,
                benchmark_score=assessment["benchmark_score"],
                score_as_of=str(assessment["as_of"]) if assessment["as_of"] else None,
                macro_label=macro_sem["regime"],
                technical_label=tech_sem["structure"],
                market_label=mkt_sem["posture"],
                # Desktop Parity Fields
                posture=mkt_sem["posture"],
                structure=tech_sem["structure"],
                conviction=assessment["benchmark_score"],
                risk_state=macro_sem["risk_state"]
            ))

        # 6. PRIORITEIT 2: Portfolio & Bot aggregations with full boundary guards
        total_invested_eur = 0.0
        total_value_eur = 0.0
        active_bots_count = 0
        active_bots = []

        try:
            for b in bot_portfolios:
                if not isinstance(b, dict):
                    continue
                stats = b.get("stats", {}) or {}
                invested = float(stats.get("invested_eur") or 0.0)
                pos_val = stats.get("position_value_eur")
                pos_val_float = float(pos_val) if pos_val is not None else invested
                
                total_invested_eur += invested
                total_value_eur += pos_val_float
                
                if b.get("is_active"):
                    active_bots_count += 1
                
                # Calculate profit percentage for this bot
                profit_pct = 0.0
                if invested > 0:
                    profit_pct = round(((pos_val_float - invested) / invested) * 100.0, 2)
                
                active_bots.append(MobileActiveBotSchema(
                    bot_id=b.get("bot_id") or b.get("id"),
                    name=b.get("name", "Onbekende Bot"),
                    symbol=b.get("symbol", "BTC"),
                    is_active=bool(b.get("is_active", False)),
                    is_live=bool(b.get("is_live", False)),
                    invested_eur=invested,
                    position_value_eur=pos_val_float if pos_val is not None else None,
                    profit_pct=profit_pct
                ))
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P2 Error during portfolio aggregation: {e}", exc_info=True)

        total_profit_pct = 0.0
        if total_invested_eur > 0:
            total_profit_pct = round(((total_value_eur - total_invested_eur) / total_invested_eur) * 100.0, 2)

        # The coach feed is the only source of proactive FINN messages. Keep
        # the legacy overview response shape until mobile consumers migrate.
        finn_briefing = MobileFinnBriefingSchema(
            greeting="", summary="", suggested_actions=[],
        )

        portfolio_overview = MobilePortfolioOverviewSchema(
            total_balance_eur=round(total_value_eur, 2),
            total_invested_eur=round(total_invested_eur, 2),
            total_profit_pct=total_profit_pct,
            active_bots_count=active_bots_count
        )

        response_payload = MobileOverviewResponse(
            user_id=user_id,
            portfolio=portfolio_overview,
            watchlist=watchlist_items,
            active_bots=active_bots,
            finn_briefing=finn_briefing,
            intelligence_events=[]
        )

        return response_payload
