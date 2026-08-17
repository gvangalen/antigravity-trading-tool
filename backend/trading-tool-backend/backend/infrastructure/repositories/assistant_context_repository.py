import logging
import re
from typing import Optional, Dict, Any, List, Tuple
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

# Import model types and repositories to reuse their well-tested database query logic sequentially
from backend.infrastructure.models import AiCategoryInsight
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository

logger = logging.getLogger(__name__)

SUPPORTED_CONTEXT_ASSET_SOURCES = (
    "explicit_prompt",
    "url",
    "page_context",
    "workspace_state",
    "user_preferences",
    "onboarding_profile",
    "conversation_state",
    "fallback",
    "unknown",
)

class AssistantContextRepository:
    """
    🛡️ AssistantContextRepository is a dedicated, production-grade repository 
    designed to orchestrate all AI Assistant data gathering.
    
    It executes all queries SEQUENTIALLY on a single shared AsyncSession instance, 
    completely eliminating task-concurrency and IllegalStateChangeError risks 
    introduced by parallel asyncio.gather calls on SQLAlchemy sessions.
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self._user_indicator_config_columns_cache: Optional[set[str]] = None
        # Re-use existing repositories by instantiating them with the same shared session
        self.user_repo = UserRepository(session)
        self.state_repo = ConversationStateRepository(session)
        self.bot_repo = BotRepository(session)
        self.market_data_repo = MarketDataRepository(session)
        self.score_repo = ScoreRepository(session)
        self.setup_repo = SetupRepository(session)
        self.report_repo = ReportRepository(session)
        self.strategy_repo = StrategyRepository(session)

    async def _get_user_indicator_config_columns(self) -> set[str]:
        if self._user_indicator_config_columns_cache is not None:
            return self._user_indicator_config_columns_cache

        try:
            result = await self.session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = 'user_indicator_configs'
                    """
                )
            )
            columns = {str(column_name) for column_name in result.scalars().all()}
        except Exception:
            columns = set()

        if not columns:
            columns = {
                "id",
                "user_id",
                "indicator",
                "category",
                "priority",
                "enabled",
                "symbol",
                "created_at",
            }

        self._user_indicator_config_columns_cache = columns
        return columns

    def _normalize_asset_symbol(self, value: Optional[str]) -> Optional[str]:
        normalized = str(value or "").strip().upper()
        return normalized if re.fullmatch(r"[A-Z0-9._:-]{1,20}", normalized or "") else None

    def _resolve_asset_context(
        self,
        *,
        explicit_symbol: Optional[str],
        page_symbol: Optional[str],
        workspace_symbol: Optional[str],
        preference_symbol: Optional[str],
        onboarding_symbol: Optional[str],
        conversation_symbol: Optional[str],
    ) -> Tuple[Optional[str], str, str, bool]:
        candidates = [
            (explicit_symbol, "explicit_prompt", "high", True),
            (page_symbol, "url", "high", True),
            (workspace_symbol, "workspace_state", "medium", True),
            (preference_symbol, "user_preferences", "medium", True),
            (onboarding_symbol, "onboarding_profile", "medium", True),
            (conversation_symbol, "conversation_state", "low", True),
        ]
        for value, source, confidence, user_scoped in candidates:
            normalized = self._normalize_asset_symbol(value)
            if normalized:
                return normalized, source, confidence, user_scoped
        return None, "unknown", "low", False

    def _coerce_int(self, value: Any) -> Optional[int]:
        try:
            coerced = int(value)
        except (TypeError, ValueError):
            return None
        return coerced if coerced > 0 else None

    def _dict_copy(self, value: Any) -> Optional[Dict[str, Any]]:
        if value is None:
            return None
        if isinstance(value, dict):
            return dict(value)
        try:
            return dict(value)
        except Exception:
            return None

    def _indicator_status(self, indicators: List[str], *, has_market_data: bool) -> Dict[str, Any]:
        if not indicators:
            return {"status": "not_configured", "configured": [], "count": 0}
        return {
            "status": "data_available" if has_market_data else "configured",
            "configured": indicators,
            "count": len(indicators),
            "fresh": bool(has_market_data),
        }

    async def build_canonical_context_graph(
        self,
        *,
        user_id: int,
        query: Optional[str] = None,
        request_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        request_context = dict(request_context or {})
        conv_state = await self.state_repo.get_state(user_id)
        user = await self.user_repo.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        slots = conv_state.get("slots") if isinstance(conv_state, dict) else {}
        slots = slots if isinstance(slots, dict) else {}

        preference_symbol = preferences.get("selected_asset") or preferences.get("active_asset")
        onboarding_symbol = preferences.get("onboarding_asset")
        workspace_symbol = (
            request_context.get("symbol")
            or request_context.get("asset")
            or slots.get("symbol")
            or slots.get("asset")
        )
        resolved_symbol, asset_source, asset_confidence, asset_user_scoped = self._resolve_asset_context(
            explicit_symbol=request_context.get("symbol") or request_context.get("asset"),
            page_symbol=request_context.get("setup_symbol"),
            workspace_symbol=workspace_symbol,
            preference_symbol=preference_symbol,
            onboarding_symbol=onboarding_symbol,
            conversation_symbol=conv_state.get("asset") if isinstance(conv_state, dict) else None,
        )

        active_setups = await self.score_repo.fetch_active_setups(user_id)
        setup_record = None
        setup_confidence = "low"
        setup_source = "missing"
        explicit_setup_id = self._coerce_int(request_context.get("setup_id"))
        if explicit_setup_id:
            setup_record = await self.setup_repo.get_setup_by_id(explicit_setup_id, user_id)
            if setup_record:
                setup_confidence = "high"
                setup_source = "explicit_setup_id"
        if not setup_record:
            active_setup = await self.setup_repo.get_active_setup(user_id)
            if active_setup and (
                not resolved_symbol
                or str(active_setup.get("symbol") or "").upper() == str(resolved_symbol or "").upper()
            ):
                setup_record = dict(active_setup)
                setup_confidence = "medium"
                setup_source = "active_setup"
        if not setup_record and resolved_symbol:
            matching_setups = [
                dict(item) for item in active_setups
                if str(item.get("symbol") or "").upper() == resolved_symbol
            ]
            if len(matching_setups) == 1:
                setup_record = matching_setups[0]
                setup_confidence = "medium"
                setup_source = "asset_matched_setup"

        explicit_strategy_id = self._coerce_int(request_context.get("strategy_id"))
        strategy_record = None
        strategy_confidence = "low"
        strategy_source = "missing"
        if explicit_strategy_id:
            strategy_record = await self.strategy_repo.get_raw_strategy_with_setup(explicit_strategy_id, user_id)
            if strategy_record:
                strategy_confidence = "high"
                strategy_source = "explicit_strategy_id"
                if setup_record and strategy_record.get("setup_id") != setup_record.get("id"):
                    strategy_record = None
                    strategy_confidence = "low"
                    strategy_source = "rejected_setup_mismatch"
        if not strategy_record and setup_record and setup_record.get("id"):
            strategy_record = await self.strategy_repo.get_strategy_by_setup(int(setup_record["id"]), user_id)
            if strategy_record:
                strategy_confidence = "medium"
                strategy_source = "setup_link"

        explicit_bot_id = self._coerce_int(request_context.get("bot_id"))
        bot_record = None
        bot_confidence = "low"
        bot_source = "missing"
        bot_configs = await self.bot_repo.get_bot_configs(user_id)
        if explicit_bot_id:
            bot_record = await self.bot_repo.get_bot_config(user_id, explicit_bot_id)
            if bot_record:
                bot_confidence = "high"
                bot_source = "explicit_bot_id"
                if strategy_record and bot_record.get("strategy_id") != strategy_record.get("id"):
                    bot_record = None
                    bot_confidence = "low"
                    bot_source = "rejected_strategy_mismatch"
        if not bot_record and strategy_record:
            linked_bots = [bot for bot in bot_configs if bot.get("strategy_id") == strategy_record.get("id")]
            if len(linked_bots) == 1:
                bot_record = dict(linked_bots[0])
                bot_confidence = "medium"
                bot_source = "strategy_link"

        market_snapshot = (
            await self.market_data_repo.get_latest_market_data(resolved_symbol)
            if resolved_symbol else None
        )
        daily_scores = await self.score_repo.fetch_daily_scores(user_id, resolved_symbol) if resolved_symbol else None
        latest_report = await self.report_repo.get_latest_report(user_id, "daily_reports")
        portfolio_intelligence = await self.bot_repo.get_portfolio_intelligence_context(user_id)
        behavioral_signals = await self.bot_repo.get_user_behavioral_signals(user_id)
        indicator_map = await self._configured_indicator_context(user_id, resolved_symbol or "BTC")
        indicators = {
            category: self._indicator_status(values, has_market_data=bool(market_snapshot))
            for category, values in indicator_map.items()
        }

        missing_context: List[str] = []
        if not resolved_symbol:
            missing_context.append("asset")
        if not setup_record:
            missing_context.append("setup")
        if setup_record and not strategy_record:
            missing_context.append("strategy")
        if strategy_record and not bot_record:
            missing_context.append("bot")
        if not daily_scores:
            missing_context.append("scores")
        if not latest_report:
            missing_context.append("latest_report")

        setup_payload = self._dict_copy(setup_record) or {}
        strategy_payload = self._dict_copy(strategy_record) or {}
        bot_payload = self._dict_copy(bot_record) or {}

        return {
            "user_id": user_id,
            "query": query,
            "profile": {
                "trader_types": preferences.get("trader_types") or [],
                "risk_profiles": preferences.get("risk_profiles") or [],
                "primary_timeframes": preferences.get("primary_timeframes") or [],
                "asset_focus": preferences.get("asset_focus") or [],
                "behavior_flags": preferences.get("behavior_flags") or [],
            },
            "asset": resolved_symbol,
            "asset_source": asset_source,
            "asset_confidence": asset_confidence,
            "asset_user_scoped": asset_user_scoped,
            "indicators": indicators,
            "setup": setup_payload,
            "strategy": strategy_payload,
            "bot": bot_payload,
            "bot_status": {
                "id": bot_payload.get("id"),
                "is_active": bool(bot_payload.get("is_active")),
                "is_live": bool(bot_payload.get("is_live")),
                "mode": bot_payload.get("mode"),
                "last_run": bot_payload.get("last_run"),
            } if bot_payload else {},
            "scores": daily_scores or {},
            "snapshots": {
                "market": market_snapshot,
                "conversation_state": conv_state or {},
            },
            "latest_report": latest_report or {},
            "review_summary": {
                "portfolio_intelligence": portfolio_intelligence or {},
                "behavioral_signals": behavioral_signals or {},
            },
            "missing_context": missing_context,
            "entity_confidence": {
                "asset": asset_confidence,
                "setup": setup_confidence,
                "strategy": strategy_confidence,
                "bot": bot_confidence,
            },
            "freshness": {
                "market": getattr(market_snapshot, "timestamp", None) if market_snapshot is not None else None,
                "report": (latest_report or {}).get("report_date"),
                "conversation_state": (conv_state or {}).get("updated_at"),
            },
            "resolution": {
                "setup_source": setup_source,
                "strategy_source": strategy_source,
                "bot_source": bot_source,
            },
        }

    async def load_runtime_context(self, user_id: int, page_symbol: Optional[str], explicit_symbol: Optional[str], intent: str) -> Dict[str, Any]:
        """
        Loads all required AI Assistant contexts sequentially to guarantee session task-safety.
        Resolves the primary focus asset symbol without applying a global asset fallback.
        """
        # 1. Fetch conversation state first
        conv_state = await self.state_repo.get_state(user_id)

        user = await self.user_repo.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        preference_symbol = preferences.get("selected_asset") or preferences.get("active_asset")
        onboarding_symbol = preferences.get("onboarding_asset")
        workspace_symbol = None
        if isinstance(conv_state, dict):
            slots = conv_state.get("slots") if isinstance(conv_state.get("slots"), dict) else {}
            workspace_symbol = slots.get("symbol") or slots.get("asset")

        resolved_symbol, asset_source, asset_confidence, asset_user_scoped = self._resolve_asset_context(
            explicit_symbol=explicit_symbol,
            page_symbol=page_symbol,
            workspace_symbol=workspace_symbol,
            preference_symbol=preference_symbol,
            onboarding_symbol=onboarding_symbol,
            conversation_symbol=conv_state.get("asset") if isinstance(conv_state, dict) else None,
        )

        # 3. Sequential fetches using the resolved symbol when present
        live_data = await self.market_data_repo.get_latest_market_data(resolved_symbol) if resolved_symbol else None
        portfolio_intelligence = await self.bot_repo.get_portfolio_intelligence_context(user_id)
        behavioral_signals = await self.bot_repo.get_user_behavioral_signals(user_id)

        # Build build-context sequentially
        context = await self.build_context_sequential(user_id, intent, resolved_symbol)

        return {
            "resolved_symbol": resolved_symbol,
            "asset": resolved_symbol,
            "asset_source": asset_source,
            "asset_confidence": asset_confidence,
            "asset_user_scoped": asset_user_scoped,
            "live_data": live_data,
            "conv_state": conv_state,
            "context": context,
            "portfolio_intelligence": portfolio_intelligence,
            "behavioral_signals": behavioral_signals,
            "user": user
        }

    async def _configured_indicator_context(self, user_id: int, asset: str) -> Dict[str, List[str]]:
        columns = await self._get_user_indicator_config_columns()
        category_select = "category" if "category" in columns else "'technical' AS category"
        conditions = ["user_id = :user_id"]
        params: Dict[str, Any] = {"user_id": user_id, "symbol": asset}

        if "enabled" in columns:
            conditions.append("enabled = TRUE")
        if "symbol" in columns:
            conditions.append(
                "("
                "symbol = :symbol "
                "OR symbol IS NULL "
                "OR symbol = 'GLOBAL'"
                ")"
            )

        order_parts: List[str] = []
        if "category" in columns:
            order_parts.append("category ASC")
        if "priority" in columns:
            order_parts.append("priority ASC")
        order_parts.append("indicator ASC")

        query = text(
            f"""
            SELECT {category_select}, indicator
            FROM user_indicator_configs
            WHERE {' AND '.join(conditions)}
            ORDER BY {', '.join(order_parts)}
            """
        )
        result = await self.session.execute(query, params)
        by_category: Dict[str, List[str]] = {"market": [], "macro": [], "technical": []}
        for row in result.mappings().all():
            category = str(row.get("category") or "").lower()
            indicator = str(row.get("indicator") or "").strip()
            if not indicator or category not in by_category:
                continue
            if indicator not in by_category[category]:
                by_category[category].append(indicator.upper() if indicator.lower() == "rsi" else indicator)
        return by_category

    async def build_context_sequential(self, user_id: int, intent: str, resolved_symbol: Optional[str] = None) -> str:
        """
        Builds historical/analysis context sequentially on the single session transaction.
        """
        context_parts = []
        today = date.today()

        if intent == "decision":
            # Scores & Setups run sequentially
            scores = await self.score_repo.get_master_score(user_id)
            setups = await self.setup_repo.get_user_setups(user_id)
            
            context_parts.append(f"CURRENT MASTER SCORE: {scores.avg_score if scores else 'N/A'}")
            context_parts.append(f"ACTIVE SETUPS: {[s.name for s in setups]}")

        elif intent == "report":
            # Latest Report
            report = await self.report_repo.get_latest_report(user_id, "daily_reports")
            context_parts.append(f"LATEST DAILY REPORT: {report.get('summary') if report else 'No report available'}")

        elif intent == "coach":
            # Strategy and History run sequentially
            start_date = today - timedelta(days=7)
            strategy = await self.strategy_repo.get_last_strategy(user_id)
            history = await self.bot_repo.get_bot_history(user_id, start_date, today)

            strat_info = "No active strategy found."
            if strategy:
                strat_data = strategy.get('data') or {}
                if isinstance(strat_data, str):
                    import json
                    strat_data = json.loads(strat_data)
                
                strat_info = {
                    "name": strategy.get("name"),
                    "type": strategy.get("setup_type"),
                    "symbol": strategy.get("setup_symbol") or strategy.get("symbol"),
                    "timeframe": strategy.get("setup_timeframe") or strategy.get("timeframe"),
                    "entry_logic": strat_data.get("entry_logic") or strat_data.get("entry", "N/A"),
                    "indicators": strat_data.get("indicators", "N/A")
                }

            trades = [h for h in history if h.get("action") in ["buy", "sell"]]
            skipped = [h for h in history if h.get("status") in ["skipped", "rejected"]]
            missed_signals = [h for h in history if h.get("status") == "skipped" and h.get("action") == "buy"]

            performance = {
                "trades_last_7d": len(trades),
                "missed_signals_count": len(missed_signals),
                "skipped_actions": len(skipped),
                "last_history": history[:5]
            }

            context_parts.append(f"COACH DATA - STRATEGY: {strat_info}")
            context_parts.append(f"COACH DATA - PERFORMANCE: {performance}")

        elif intent == "analysis":
            # Market Trends & Scores run sequentially only when an asset is known.
            categories = ["macro", "market", "technical"]
            category_data = {}

            if resolved_symbol:
                for cat in categories:
                    stmt = select(AiCategoryInsight).where(
                        AiCategoryInsight.user_id == user_id,
                        AiCategoryInsight.category == cat,
                        AiCategoryInsight.symbol == resolved_symbol,
                    ).order_by(AiCategoryInsight.date.desc()).limit(1)

                    res = await self.session.execute(stmt)
                    user_insight = res.scalars().first()

                    if user_insight:
                        category_data[cat] = {
                            "summary": user_insight.summary,
                            "bias": user_insight.bias,
                            "score": float(user_insight.avg_score or 0)
                        }
            else:
                category_data["asset_resolution"] = {
                    "status": "unknown",
                    "message": "No user-scoped asset could be resolved for analysis context.",
                }

            context_parts.append(f"AI ANALYSIS CONTEXT: {category_data}")

        if not context_parts:
            context_parts.append("General assistance mode. No specific deep context loaded.")

        return "\n".join(context_parts)
