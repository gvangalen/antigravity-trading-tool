import logging
from typing import Optional, Dict, Any, List
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

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
        # Re-use existing repositories by instantiating them with the same shared session
        self.user_repo = UserRepository(session)
        self.state_repo = ConversationStateRepository(session)
        self.bot_repo = BotRepository(session)
        self.market_data_repo = MarketDataRepository(session)
        self.score_repo = ScoreRepository(session)
        self.setup_repo = SetupRepository(session)
        self.report_repo = ReportRepository(session)
        self.strategy_repo = StrategyRepository(session)

    async def load_runtime_context(self, user_id: int, page_symbol: Optional[str], explicit_symbol: Optional[str], intent: str) -> Dict[str, Any]:
        """
        Loads all required AI Assistant contexts sequentially to guarantee session task-safety.
        Resolves the primary focus asset symbol using a strict priority hierarchy:
        1. Explicit symbol mention in user query
        2. Live active page asset (from context_data)
        3. Active conversation state asset (from conversation_state)
        4. Fallback to BTC
        """
        # 1. Fetch conversation state first
        conv_state = await self.state_repo.get_state(user_id)
        
        # 2. Priority Symbol Resolution
        resolved_symbol = "BTC"
        if explicit_symbol:
            resolved_symbol = explicit_symbol
        elif page_symbol:
            resolved_symbol = page_symbol
        elif conv_state and conv_state.get("asset"):
            resolved_symbol = conv_state["asset"]
            
        # 3. Sequential fetches using the resolved symbol
        live_data = await self.market_data_repo.get_latest_market_data(resolved_symbol)
        portfolio_intelligence = await self.bot_repo.get_portfolio_intelligence_context(user_id)
        behavioral_signals = await self.bot_repo.get_user_behavioral_signals(user_id)
        user = await self.user_repo.get_by_id(user_id)
        
        # Build build-context sequentially
        context = await self.build_context_sequential(user_id, intent)
        
        return {
            "resolved_symbol": resolved_symbol,
            "live_data": live_data,
            "conv_state": conv_state,
            "context": context,
            "portfolio_intelligence": portfolio_intelligence,
            "behavioral_signals": behavioral_signals,
            "user": user
        }

    async def build_context_sequential(self, user_id: int, intent: str) -> str:
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
            # Market Trends & Scores with Global Fallback run sequentially
            categories = ["macro", "market", "technical"]
            category_data = {}

            for cat in categories:
                stmt = select(AiCategoryInsight).where(
                    AiCategoryInsight.user_id == user_id,
                    AiCategoryInsight.category == cat
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
                    global_insight = await self.score_repo.get_global_insight(cat)
                    if global_insight:
                        category_data[cat] = {
                            "summary": global_insight["summary"],
                            "bias": global_insight["bias"],
                            "score": float(global_insight["avg_score"] or 0),
                            "note": "GLOBAL_FALLBACK"
                        }

            context_parts.append(f"AI ANALYSIS CONTEXT: {category_data}")

        if not context_parts:
            context_parts.append("General assistance mode. No specific deep context loaded.")

        return "\n".join(context_parts)
