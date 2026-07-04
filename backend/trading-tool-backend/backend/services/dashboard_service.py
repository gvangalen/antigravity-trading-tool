import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from fastapi import HTTPException

from backend.infrastructure.repositories.dashboard_repository import DashboardRepository
from backend.services.platform_metrics import record_latency_sample
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

# =========================================================
# SYNCHRONOUS WRAPPER FOR SCORING ENGINE
# =========================================================
def sync_get_scores_for_symbol(user_id: int, symbol: str = "BTC") -> dict:
    from backend.utils.scoring_utils import get_scores_for_symbol
    try:
        return get_scores_for_symbol(user_id=user_id, symbol=symbol, include_metadata=True)
    except TypeError:
        return get_scores_for_symbol(include_metadata=True)

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
            
            # Execute Sync Scoring Request
            scores = await asyncio.to_thread(sync_get_scores_for_symbol, user_id, symbol)
            
            macro_score = scores.get("macro_score", 0)
            technical_score = scores.get("technical_score", 0)
            market_score = scores.get("market_score", 0)
            
            # GET DYNAMIC SETUP SCORE
            from backend.services.setup_service import SetupService
            setup_service = SetupService(self.session)
            active_setup_dict = await setup_service.get_active_setup(user_id, symbol)
            active_setup = active_setup_dict.get("active")
            setup_score = active_setup.get("score", 0) if active_setup else 0
            
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
        rows = await self.repository.get_top_setups(user_id)
        for row in rows:
            if row.get("timestamp") and hasattr(row["timestamp"], "isoformat"):
                row["timestamp"] = row["timestamp"].isoformat()
        return rows

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

    async def get_mobile_overview(self, user_id: int, bypass_cache: bool = False) -> MobileOverviewResponse:
        logger.info(f"🔄 [MobileOverview] Executing hardened composition for user_id={user_id}.")

        # 2. Setup symbols and default fallback structs
        # Fetch real watchlist for user from database
        query = text("SELECT symbol FROM watchlists WHERE user_id = :user_id")
        result = await self.session.execute(query, {"user_id": user_id})
        symbols = [row.symbol.upper() for row in result.fetchall()]
        if not symbols:
            symbols = ["BTC", "ETH", "SOL"]
            
        # We declare safe defaults for all sub-components so they are populated even under failure
        prices_data = {s: {"price": None, "change_24h": None} for s in symbols}
        bot_portfolios = []
        ai_insight = {}
        raw_intel_events = []

        # 3. Run DB-backed components sequentially. A single AsyncSession must
        # not be shared across concurrent DB awaits.
        try:
            prices_data = await self.repository.get_latest_prices_and_changes(user_id, symbols) or prices_data
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P1 Error: prices failed: {e}", exc_info=True)

        try:
            from backend.services.bot_service import BotService
            bot_service = BotService(self.session)
            bot_portfolios = await bot_service.get_bot_portfolios(user_id) or []
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P2 Error: bot portfolios failed: {e}", exc_info=True)

        try:
            from backend.services.intelligence_event_service import IntelligenceEventService
            from backend.infrastructure.repositories.bot_repository import BotRepository
            from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
            from backend.infrastructure.repositories.score_repository import ScoreRepository
            
            intel_service = IntelligenceEventService(
                session=self.session,
                bot_repo=BotRepository(self.session),
                market_data_repo=MarketDataRepository(self.session),
                score_repo=ScoreRepository(self.session)
            )
            raw_intel_events = await intel_service.evaluate_and_generate_events(user_id) or []
        except Exception as e:
            logger.error(f"❌ [MobileOverview] P3 Error: intelligence events failed: {e}", exc_info=True)

        try:
            from backend.services.finn_plan_service import FinnPlanService

            finn = FinnPlanService(self.session)
            daily = await finn.build_daily_coach_response(
                user_id,
                "Wat moet ik vandaag doen met mijn BTC setup?",
                {"symbol": "BTC", "page": "mobile_overview"},
            )
            analysis = (daily.get("state") or {}).get("analysis") or {}
            ai_insight = {
                "daily_coach": analysis,
                "briefing_text": daily.get("response"),
                "suggested_actions": daily.get("suggested_actions") or analysis.get("suggested_actions") or [],
            }
        except Exception as e:
            logger.error(f"⚠️ [MobileOverview] Deterministic Finn briefing failed: {e}", exc_info=True)

        # 5. PRIORITEIT 1: Process watchlist scores dynamically via standard score engine
        from backend.services.intelligence_semantics import get_macro_semantics, get_technical_semantics, get_market_semantics
        watchlist_items = []
        for sym in symbols:
            try:
                scores = await asyncio.to_thread(sync_get_scores_for_symbol, user_id, sym)
            except Exception as e:
                logger.error(f"⚠️ [MobileOverview] P1 Warning: Failed to fetch scores for {sym}: {e}")
                scores = {}

            price_info = prices_data.get(sym, {}) if isinstance(prices_data, dict) else {}
            macro_val = float(scores.get("macro_score", 0))
            tech_val = float(scores.get("technical_score", 0))
            mkt_val = float(scores.get("market_score", 0))

            macro_sem = get_macro_semantics(macro_val)
            tech_sem = get_technical_semantics(tech_val)
            mkt_sem = get_market_semantics(mkt_val)

            watchlist_items.append(MobileAssetWatchlistSchema(
                symbol=sym,
                price=price_info.get("price"),
                change_24h=price_info.get("change_24h"),
                macro_score=macro_val,
                technical_score=tech_val,
                market_score=mkt_val,
                setup_score=float(scores.get("setup_score", 0)),
                macro_label=macro_sem["regime"],
                technical_label=tech_sem["structure"],
                market_label=mkt_sem["posture"],
                # Desktop Parity Fields
                posture=mkt_sem["posture"],
                structure=tech_sem["structure"],
                conviction=float(int((macro_val + tech_val + mkt_val) / 3)),
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

        # 7. PRIORITEIT 3: Dutch FINN Briefing with bulletproof fallback logic
        first_name = "Handelaar"
        try:
            user_repo = UserRepository(self.session)
            user_obj = await user_repo.get_by_id(user_id)
            if user_obj and hasattr(user_obj, "first_name") and user_obj.first_name:
                first_name = user_obj.first_name
        except Exception as e:
            logger.error(f"⚠️ [MobileOverview] P3 Warning: Failed to retrieve user object: {e}")

        greeting = f"Hallo {first_name}!"
        summary = "Je portfolio is stabiel. Er zijn geen directe waarschuwingen voor je actieve setups."
        suggested_actions = ["DCA setup maken", "Mijn bots bekijken", "Risico aanpassen"]

        # If AI insights succeeded, unpack them safely
        if isinstance(ai_insight, dict):
            daily_coach = ai_insight.get("daily_coach")
            if isinstance(daily_coach, dict):
                stance = daily_coach.get("stance")
                asset = daily_coach.get("asset", "BTC")
                blockers = daily_coach.get("blockers") or []
                if stance == "plan_is_active":
                    summary = f"{asset}: je plan is vandaag actief volgens je eigen ranges. Review bot-proposals handmatig voor uitvoering."
                elif stance == "wait_for_scores":
                    summary = f"{asset}: daily scores ontbreken nog; Finn wacht met een actief/inactief oordeel."
                elif blockers:
                    first = blockers[0]
                    summary = (
                        f"{asset}: wachten. {first.get('category')} score {first.get('score')} "
                        f"valt buiten je range {first.get('range')}."
                    )
                else:
                    summary = ai_insight.get("briefing_text") or summary
            insight_market = ai_insight.get("market_insight", {})
            if isinstance(insight_market, dict):
                insight_conclusion = insight_market.get("conclusion")
                if insight_conclusion and not ai_insight.get("daily_coach"):
                    summary = insight_conclusion
            
            ai_suggested = ai_insight.get("suggested_actions")
            if isinstance(ai_suggested, list) and len(ai_suggested) > 0:
                suggested_actions = ai_suggested

        finn_briefing = MobileFinnBriefingSchema(
            greeting=greeting,
            summary=summary,
            suggested_actions=suggested_actions
        )

        portfolio_overview = MobilePortfolioOverviewSchema(
            total_balance_eur=round(total_value_eur, 2),
            total_invested_eur=round(total_invested_eur, 2),
            total_profit_pct=total_profit_pct,
            active_bots_count=active_bots_count
        )

        # 8. Format and assemble intelligence events
        formatted_events = []
        for ev in raw_intel_events:
            event_id = _safe_event_attr(ev, "id")
            if event_id is None:
                continue
            formatted_events.append(MobileIntelligenceEventSchema(
                id=event_id,
                type=_safe_event_attr(ev, "type", "info"),
                symbol=_safe_event_attr(ev, "symbol"),
                title=_safe_event_attr(ev, "title", "FINN melding"),
                description=_safe_event_attr(ev, "description", ""),
                severity=_safe_event_attr(ev, "severity", "info"),
                created_at=_safe_event_attr(ev, "created_at", datetime.now(timezone.utc))
            ))

        response_payload = MobileOverviewResponse(
            user_id=user_id,
            portfolio=portfolio_overview,
            watchlist=watchlist_items,
            active_bots=active_bots,
            finn_briefing=finn_briefing,
            intelligence_events=formatted_events
        )

        return response_payload
