import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from backend.infrastructure.models import AiCategoryInsight

from backend.ai_agents.ai_assistant_prompts import get_role_prompt
from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository

logger = logging.getLogger(__name__)

class AiAssistantService:
    def __init__(
        self,
        score_repo: ScoreRepository,
        setup_repo: SetupRepository,
        report_repo: ReportRepository,
        bot_repo: BotRepository,
        user_repo: UserRepository,
        market_data_repo: MarketDataRepository,
        strategy_repo: StrategyRepository,
        ai_gateway: AiGateway
    ):
        self.score_repo = score_repo
        self.setup_repo = setup_repo
        self.report_repo = report_repo
        self.bot_repo = bot_repo
        self.user_repo = user_repo
        self.market_data_repo = market_data_repo
        self.strategy_repo = strategy_repo
        self.ai_gateway = ai_gateway

    async def get_chat_response(self, user_id: int, user_query: str, context_data: Optional[Dict[str, str]] = None) -> tuple[str, Optional[Dict[str, Any]]]:
        # 1. Classify Intent (Rule-based V1)
        intent = self._classify_intent(user_query)
        logger.info(f"🧠 Assistant Chat Intent: {intent} for query: {user_query}")
        
        # 1.5 Fetch LIVE Market Context
        symbol = context_data.get("symbol", "BTC") if context_data else "BTC"
        live_data = await self.market_data_repo.get_latest_market_data(symbol)
        live_context = "No live market data available in database."
        if live_data:
            live_context = (
                f"CURRENT LIVE DATA (TRUTH):\n"
                f"Symbol: {symbol}\n"
                f"Price: ${live_data.price:,.2f}\n"
                f"24h Change: {live_data.change_24h}%\n"
                f"Last Updated: {live_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"INSTRUCTION: Use THIS price for any current price questions. Do NOT guess."
            )

        # 2. Build Context
        context = await self._build_context(user_id, intent)

        # 3. Route Agent (Select Role)
        role_key = self._route_role(intent)
        
        # 4. Get User Preferences
        user = await self.user_repo.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}

        # 5. Build System Prompt
        system_role = get_role_prompt(role_key, preferences)

        # 6. Generate Response via GATEWAY using JSON mode to allow action parameters
        prompt = (
            f"USER QUERY: {user_query}\n\n"
            f"LIVE MARKET CONTEXT:\n{live_context}\n\n"
            f"HISTORICAL/ANALYSIS CONTEXT:\n{context}\n\n"
            f"FRONTEND METADATA:\n{context_data}"
        )
        
        system_role_json = (
            system_role + 
            "\n\nIMPORTANT: You must return a JSON object with exactly two fields:\n"
            "- 'response': (string) your conversational response to the user's message in Dutch.\n"
            "- 'action': (object or null) if the user explicitly asks to add a coin to their watchlist, "
            "build/create/generate a setup or strategy, or deploy/create a bot, populate this object. "
            "Otherwise, set 'action' to null.\n"
            "The 'action' object must have:\n"
            "   * 'type': one of ['add_to_watchlist', 'open_setup_page', 'generate_strategy', 'open_bot_draft']\n"
            "   * 'symbol': the relevant crypto symbol (e.g., 'SOL', 'BTC')\n"
            "   * 'params': (object) optional parameters like risk (aggressive, conservative, balanced), mode (paper, live), budget (int)\n\n"
            "Example of action:\n"
            "If user says: 'Voeg SOL toe aan mn watchlist', return:\n"
            "{\n"
            "  \"response\": \"Ik ga SOL toevoegen aan je watchlist!\",\n"
            "  \"action\": {\"type\": \"add_to_watchlist\", \"symbol\": \"SOL\", \"params\": {}}\n"
            "}"
        )

        schema = {
            "type": "object",
            "properties": {
                "response": {"type": "string"},
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["add_to_watchlist", "open_setup_page", "generate_strategy", "open_bot_draft"]},
                        "symbol": {"type": "string"},
                        "params": {"type": "object"}
                    },
                    "required": ["type"],
                    "nullable": True
                }
            },
            "required": ["response", "action"]
        }

        response_data = await self.ai_gateway.ask(
            user_id=user_id, 
            prompt=prompt, 
            system_role=system_role_json, 
            mode="json",
            schema=schema,
            purpose=f"chat_{intent}"
        )

        # Robust parsing of JSON-mode response
        chat_text = "⚠️ Kon geen analyse ophalen. Probeer opnieuw."
        action = None

        if response_data:
            if isinstance(response_data, dict):
                chat_text = response_data.get("response", chat_text)
                action = response_data.get("action")
            elif isinstance(response_data, str):
                # Fallback if cached or raw string returned
                try:
                    import json
                    parsed = json.loads(response_data)
                    if isinstance(parsed, dict):
                        chat_text = parsed.get("response", chat_text)
                        action = parsed.get("action")
                    else:
                        chat_text = response_data
                except Exception:
                    chat_text = response_data

        # 7. Selective Preference Update (Optional/Explicit feedback)
        await self._handle_implicit_feedback(user_id, user_query)

        return chat_text, action

    async def get_assistant_insight(self, user_id: int, context_data: Dict[str, str]) -> Dict[str, Any]:
        # 1. Fetch Contexts
        market_context = await self._build_context(user_id, "analysis")
        bot_context = await self._build_context(user_id, "coach")
        
        # 1.5 Fetch LIVE Market Context
        symbol = context_data.get("symbol", "BTC")
        live_data = await self.market_data_repo.get_latest_market_data(symbol)
        live_context = "No live data available."
        if live_data:
            live_context = (
                f"CURRENT PRICE: ${live_data.price:,.2f}\n"
                f"24H CHANGE: {live_data.change_24h}%\n"
                f"TIMESTAMP: {live_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        # 2. Get User Preferences & Name
        user = await self.user_repo.get_by_id(user_id)
        preferences = getattr(user, "ai_preferences", {}) or {}
        user_name = getattr(user, "first_name", "Trader")

        # 3. Build System Prompt (Combined role for speed/brevity)
        raw_system_role = get_role_prompt("combined_insight", preferences)
        page_type = context_data.get("page_type", "Dashboard")
        timeframe = context_data.get("timeframe", "Snapshot")
        
        # Manually replace placeholders in the system role task description
        system_role = raw_system_role.replace("{user_name}", user_name) \
                                     .replace("{page}", page_type) \
                                     .replace("{symbol}", symbol)

        # 4. Generate Insight via GATEWAY (Single Call)
        prompt = (
            f"GENERATE ACTION-ORIENTED TRADING INSIGHT\n"
            f"--- CONTEXT DATA ---\n"
            f"USER: {user_name} | PAGE: {page_type} | ASSET: {symbol} | TIME: {timeframe}\n\n"
            f"--- INSTRUCTIONS ---\n"
            f"- GREETING: Exactly 1 sentence (Hoi {user_name}, BTC/market summary...).\n"
            f"- CONCLUSION/ACTION: Exactly 1 sentence each.\n"
            f"- WHY: Technical reasoning (RSI/price) in max 2 sentences.\n"
            f"- terminology: refer to as 'coach' advice.\n"
            f"- Be extremely concise.\n\n"
            f"FALLBACK: If strategy is missing, suggest setup for {symbol}."
        )

        insight = await self.ai_gateway.ask(
            user_id=user_id,
            prompt=prompt,
            system_role=system_role,
            mode="json",
            purpose="assistant", # Cache-friendly category
            symbol=symbol,
            timeframe=timeframe
        )

        if not insight or not isinstance(insight, dict):
            # Safe Fallback
            return {
                "greeting": f"Hoi {user_name}, ik monitor de {page_type} pagina voor je.",
                "bot_insight": {
                    "conclusion": "Geen actieve strategie gevonden.",
                    "action": f"Maak een setup voor {symbol} om coaching te ontvangen.",
                    "why": "Er is geen configuratie beschikbaar om te analyseren."
                },
                "market_insight": {
                    "conclusion": "Marktdata wordt verwerkt.",
                    "action": "Monitor de huidige trend op de grafiek.",
                    "why": "Scan loopt nog op live data inputs."
                }
            }

        return insight

    def _classify_intent(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["score", "status", "cijfers", "hoe sta ik erbij"]):
            return "decision"
        if any(w in q for w in ["rapport", "uitleg", "samenvatting", "insight"]):
            return "report"
        if any(w in q for w in ["coach", "discipline", "fout", "gedrag", "trades", "acties", "verbeter", "optimaliseer", "niet koopt", "waarom koopt"]):
            return "coach"
        if any(w in q for w in ["analyse", "diep", "waarom", "patroon", "markt"]):
            return "analysis"
        return "general"

    def _route_role(self, intent: str) -> str:
        mapping = {
            "decision": "assistant",
            "report": "editor",
            "coach": "coach",
            "analysis": "analyst",
            "general": "assistant"
        }
        return mapping.get(intent, "assistant")

    async def _build_context(self, user_id: int, intent: str) -> str:
        context_parts = []
        today = date.today()

        if intent == "decision":
            # Scores & Setups
            scores = await self.score_repo.get_master_score(user_id)
            setups = await self.setup_repo.get_user_setups(user_id)
            context_parts.append(f"CURRENT MASTER SCORE: {scores.avg_score if scores else 'N/A'}")
            context_parts.append(f"ACTIVE SETUPS: {[s.name for s in setups]}")

        elif intent == "report":
            # Latest Report
            report = await self.report_repo.get_latest_report(user_id, "daily_reports")
            context_parts.append(f"LATEST DAILY REPORT: {report.get('summary') if report else 'No report available'}")

        elif intent == "coach":
            # 1. Fetch Latest Strategy
            strategy = await self.strategy_repo.get_last_strategy(user_id)
            strat_info = "No active strategy found."
            if strategy:
                # strategy['data'] contains the JSON config (indicator thresholds, etc.)
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

            # 2. Performance: Last 7 days
            start_date = today - timedelta(days=7)
            history = await self.bot_repo.get_bot_history(user_id, start_date, today)
            
            trades = [h for h in history if h.get("action") in ["buy", "sell"]]
            skipped = [h for h in history if h.get("status") in ["skipped", "rejected"]]
            missed_signals = [h for h in history if h.get("status") == "skipped" and h.get("action") == "buy"]

            performance = {
                "trades_last_7d": len(trades),
                "missed_signals_count": len(missed_signals),
                "skipped_actions": len(skipped),
                "last_history": history[:5] # Last 5 for context
            }

            context_parts.append(f"COACH DATA - STRATEGY: {strat_info}")
            context_parts.append(f"COACH DATA - PERFORMANCE: {performance}")

        elif intent == "analysis":
            # 📊 Market Trends & Scores with Global Fallback
            categories = ["macro", "market", "technical"]
            category_data = {}

            for cat in categories:
                # 1. Try User-specific insight
                stmt = select(AiCategoryInsight).where(
                    AiCategoryInsight.user_id == user_id,
                    AiCategoryInsight.category == cat
                ).order_by(AiCategoryInsight.date.desc()).limit(1)
                
                res = await self.score_repo.db.execute(stmt)
                user_insight = res.scalars().first()

                if user_insight:
                    category_data[cat] = {
                        "summary": user_insight.summary,
                        "bias": user_insight.bias,
                        "score": float(user_insight.avg_score or 0)
                    }
                else:
                    # 2. Fallback to Global Intelligence
                    global_insight = await self.score_repo.get_global_insight(cat)
                    if global_insight:
                        category_data[cat] = {
                            "summary": global_insight["summary"],
                            "bias": global_insight["bias"],
                            "score": float(global_insight["avg_score"] or 0),
                            "note": "GLOBAL_FALLBACK"
                        }

            context_parts.append(f"AI ANALYSIS CONTEXT: {category_data}")

        # Always add basic context if needed or fallbacks
        if not context_parts:
            context_parts.append("General assistance mode. No specific deep context loaded.")

        return "\n".join(context_parts)

    async def _handle_implicit_feedback(self, user_id: int, query: str):
        # Selective preference updates only for explicit style/tone feedback
        q = query.lower()
        updates = {}
        if "korter" in q or "bondiger" in q:
            updates["detail_level"] = "concise"
        elif "uitgebreider" in q or "meer detail" in q:
            updates["detail_level"] = "detailed"
        elif "agressiever" in q or "harder" in q:
            updates["tone"] = "aggressive"
        elif "vriendelijker" in q:
            updates["tone"] = "friendly"
        
        if updates:
            await self.user_repo.update_ai_preferences(user_id, updates)
            logger.info(f"Updated AI preferences for user {user_id}: {updates}")
