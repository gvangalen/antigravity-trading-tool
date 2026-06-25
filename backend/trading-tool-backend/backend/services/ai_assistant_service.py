import logging
import time
import uuid
import asyncio
import os
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, AsyncGenerator
from sqlalchemy import select, update, and_, desc, text
from backend.infrastructure.models import AiCategoryInsight, ChatSession, ChatMessage, AiIntelligenceEvent, AiPendingAction

from backend.ai_agents.ai_assistant_prompts import get_role_prompt
from backend.services.ai_gateway import AiGateway
from backend.services.ai_usage_log_compat import AI_USAGE_LOG_COLUMN_ORDER, filter_ai_usage_log_values
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.services.platform_metrics import record_latency_sample
from backend.services.setup_service import SetupService
from backend.services.finn_plan_service import FinnPlanService
from backend.services.trader_profile_service import build_trader_profile_context

logger = logging.getLogger(__name__)

ASSISTANT_CONTEXT_CACHE_TTL_SECONDS = int(os.getenv("ASSISTANT_CONTEXT_CACHE_TTL_SECONDS", "20"))
_assistant_context_cache: Dict[str, Dict[str, Any]] = {}
_ai_usage_log_supported_columns: Optional[set[str]] = None


def _get_cached_assistant_context(cache_key: str) -> Optional[str]:
    cached = _assistant_context_cache.get(cache_key)
    if not cached:
        return None
    if float(cached.get("expires_at") or 0) <= time.time():
        _assistant_context_cache.pop(cache_key, None)
        return None
    value = cached.get("value")
    return str(value) if value is not None else None


def _store_cached_assistant_context(cache_key: str, context: str) -> None:
    _assistant_context_cache[cache_key] = {
        "expires_at": time.time() + max(1, ASSISTANT_CONTEXT_CACHE_TTL_SECONDS),
        "value": str(context),
    }


def _build_adaptive_profile_str(
    preferences: Optional[dict],
    behavioral_signals: Optional[dict],
    user_name: str,
) -> str:
    prefs = preferences or {}
    profile_context = build_trader_profile_context(prefs)
    profile = profile_context.get("trader_profile") or {}
    stated_exp = str(prefs.get("experience_level", "beginner"))
    stated_risk = str(prefs.get("risk_profile", "balanced"))

    def _join(values: Optional[List[str]]) -> str:
        payload = values or []
        return ", ".join(payload) if payload else "not_set"

    return (
        f"ADAPTIVE PERSONALIZATION PROFILE:\n"
        f"- Stated Experience Level (Preference): {stated_exp.upper()}\n"
        f"- Stated Risk Profile (Preference): {stated_risk.upper()}\n"
        f"- Trader Types: {_join(profile.get('trader_types'))}\n"
        f"- Preferred Timeframes: {_join(profile.get('primary_timeframes'))}\n"
        f"- Asset Focus: {_join(profile.get('asset_focus'))}\n"
        f"- Investment Goals: {_join(profile.get('investment_goals'))}\n"
        f"- Experience Levels: {_join(profile.get('experience_levels'))}\n"
        f"- Risk Profiles: {_join(profile.get('risk_profiles'))}\n"
        f"- Behavior Flags: {_join(profile.get('behavior_flags'))}\n"
        f"- Behavioral Trading Signals:\n"
        f"  * Configured Custom Setups: {behavioral_signals['setups_count'] if behavioral_signals else 0}\n"
        f"  * Configured Custom Strategies: {behavioral_signals['strategies_count'] if behavioral_signals else 0}\n"
        f"  * Active Trading Bots: {behavioral_signals['bots_count'] if behavioral_signals else 0}\n"
        f"  * Cumulative Custom Actions: {behavioral_signals['total_custom_configs'] if behavioral_signals else 0}\n"
        f"  * Behavioral Maturity Category: {behavioral_signals['behavioral_level'] if behavioral_signals else 'novice'}\n\n"
        f"ADAPTIVE INTELLIGENCE INSTRUCTIONS:\n"
        f"1. SUBTLE STYLING (CRITICAL): Under no circumstances greet the user with labels like 'Hallo beginner' or 'Als ervaren handelaar'. Adapt your style completely under the hood to feel premium, natural, and custom-tailored.\n"
        f"2. BALANCING EXPERIENCES (STATED vs. BEHAVIORAL):\n"
        f"   - If both Stated Preference and Behavioral signals agree on beginner/novice level: Explain concepts gently, define trading terms (like DCA, RSI, average entry, MACD) using intuitive analogies, and use a supportive, encouraging coaching style.\n"
        f"   - If both Stated Preference and Behavioral signals agree on advanced/experienced level: Speak using dense, professional, trade-oriented parameters. Skip definitions. Present metrics directly and keep explanations brief and bulleted.\n"
        f"   - If Stated Preference is 'advanced' but Behavioral signals are 'Novice' (0 setups/bots): Do not use overly basic analogies, but explain setup requirements carefully and step-by-step anyway. Use professional terms but ensure educational clarity.\n"
        f"3. PROFILE FITTING:\n"
        f"   - If trader types include investor or dca_investor, reduce short-term urgency and reinforce plan consistency over micro timing.\n"
        f"   - If trader types include swing_trader, emphasize 4H/1D structure, patience around entries, and clean invalidation logic.\n"
        f"   - If trader types include day_trader or scalper, acknowledge intraday timing and momentum, but do not let that override the stated risk profile.\n"
        f"   - If asset focus excludes the current asset class, make that mismatch explicit before recommending action.\n"
        f"4. CALIBRATING RISK THRESHOLDS & COACHING:\n"
        f"   - CONSERVATIVE PROFILE: Focus on downside protection and capital preservation. Proactively warn {user_name} if more than 40% of total equity is concentrated in a single volatile coin or if cash is low (<20%).\n"
        f"   - BALANCED PROFILE: Follow default risk limits (warn at >60% concentration or <10% cash) and recommend balanced asset-matching.\n"
        f"   - AGGRESSIVE PROFILE: Align with higher exposure allocations, but reinforce trading discipline. Warn only if asset concentration exceeds 80% and emphasize strict take-profit execution limits.\n"
        f"5. CASUAL PROFILE SIGNALS & CONFIDENCE PROPOSALS:\n"
        f"   - If {user_name} makes a casual statement indicating a level or risk that does NOT match the active profile: adapt for the current turn, but do not mutate the permanent profile automatically.\n"
    )


def _resolve_locale(preferences: Optional[dict]) -> str:
    locale = str((preferences or {}).get("locale") or "nl").strip().lower()
    return "en" if locale.startswith("en") else "nl"


def _response_language_name(preferences: Optional[dict]) -> str:
    return "English" if _resolve_locale(preferences) == "en" else "Dutch"


def _localized_example_text(preferences: Optional[dict], key: str, symbol: str) -> str:
    locale = _resolve_locale(preferences)
    examples = {
        "no_setup": {
            "nl": f"Er is nog geen setup voor {symbol}, laten we die eerst maken.",
            "en": f"There is no setup for {symbol} yet, so let’s create that first.",
        },
        "no_strategy": {
            "nl": f"Er is nog geen strategie voor {symbol}, laten we die eerst ontwerpen.",
            "en": f"There is no strategy for {symbol} yet, so let’s design that first.",
        },
        "no_setup_nor_strategy": {
            "nl": f"Er is nog geen setup of strategie voor {symbol}, dus we beginnen bij de basis met een setup.",
            "en": f"There is no setup or strategy for {symbol} yet, so we should start with a setup first.",
        },
        "setup_type_question": {
            "nl": "Wil je een DCA of trade setup?",
            "en": "Do you want a DCA setup or a trade setup?",
        },
    }
    return examples.get(key, {}).get(locale) or examples.get(key, {}).get("nl") or ""

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
        state_repo: ConversationStateRepository,
        ai_gateway: AiGateway,
        context_repo: Optional[Any] = None
    ):
        self.score_repo = score_repo
        self.setup_repo = setup_repo
        self.report_repo = report_repo
        self.bot_repo = bot_repo
        self.user_repo = user_repo
        self.market_data_repo = market_data_repo
        self.strategy_repo = strategy_repo
        self.state_repo = state_repo
        self.ai_gateway = ai_gateway
        self.context_repo = context_repo
        self._active_preferences: Dict[str, Any] = {}

    def generate_clean_title(self, query: str) -> str:
        q_lower = query.lower()
        if "dca" in q_lower:
            asset = "BTC"
            if "eth" in q_lower:
                asset = "ETH"
            elif "sol" in q_lower:
                asset = "SOL"
            return f"DCA Setup {asset}"
        elif "bot" in q_lower or "start" in q_lower:
            return "Bot Activeren/Aanpassen"
        elif "macro" in q_lower or "score" in q_lower:
            return "Markt & Macro Analyse"
        elif "rsi" in q_lower or "macd" in q_lower or "technic" in q_lower:
            return "Technische Indicatoren"
        elif "sol" in q_lower:
            return "Solana Analyse"
        elif "eth" in q_lower:
            return "Ethereum Vraag"
        words = query.strip().split()
        if words:
            import re
            clean_words = []
            for w in words[:4]:
                cw = re.sub(r'[^\w]', '', w)
                if cw:
                    clean_words.append(cw)
            if clean_words:
                title = " ".join(clean_words).capitalize()
                if len(words) > 4:
                    title += "..."
                return title
        return "Nieuw gesprek"

    async def get_chat_response(
        self, 
        user_id: int, 
        user_query: str, 
        history: Optional[List[Dict[str, Any]]] = None,
        context_data: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[List[str]], Optional[str]]:
        # Start response time tracking
        self.start_overall_time = time.perf_counter()
        self.trace_id = trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
        
        # Resolve or create persistent Chat Session if requested
        actual_session_id = None
        if session_id:
            if session_id == "new":
                actual_session_id = str(uuid.uuid4())
                new_session = ChatSession(
                    id=actual_session_id,
                    user_id=user_id,
                    title=self.generate_clean_title(user_query),
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.state_repo.session.add(new_session)
                await self.state_repo.session.flush()
            else:
                actual_session_id = session_id
                session_stmt = select(ChatSession).where(ChatSession.id == actual_session_id, ChatSession.user_id == user_id)
                session_res = await self.state_repo.session.execute(session_stmt)
                existing_session = session_res.scalars().first()
                if not existing_session:
                    actual_session_id = str(uuid.uuid4())
                    new_session = ChatSession(
                        id=actual_session_id,
                        user_id=user_id,
                        title=self.generate_clean_title(user_query),
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    self.state_repo.session.add(new_session)
                    await self.state_repo.session.flush()
                else:
                    if not history:
                        history = []
                        msg_stmt = select(ChatMessage).where(ChatMessage.session_id == actual_session_id).order_by(ChatMessage.created_at.asc())
                        msg_res = await self.state_repo.session.execute(msg_stmt)
                        db_messages = msg_res.scalars().all()
                        for m in db_messages:
                            history.append({
                                "role": m.role,
                                "text": m.content
                            })

        # 1. Classify Intent (Rule-based V1)
        intent = self._classify_intent(user_query)
        logger.info(f"🧠 Assistant Chat Intent: {intent} for query: {user_query}")
        
        # 1.1 Conversational Abort/Reset Engine Interceptor (Bypasses DB gather and LLM calls entirely!)
        abort_triggers = ["stop", "annuleer", "annuleren", "laat maar", "reset", "opnieuw beginnen", "wis alles", "wis setup"]
        q_lower = user_query.strip().lower()
        import re
        q_clean = re.sub(r'[^\w\s]', '', q_lower)
        
        is_abort = False
        if any(trigger in q_clean for trigger in abort_triggers):
            # Exclude trading stop terms that contain 'stop'
            trading_stop_terms = ["stop-loss", "stop loss", "stoploss", "stop-limit", "stop limit", "stoplimit"]
            if any(term in q_lower for term in trading_stop_terms):
                is_abort = False
            else:
                is_abort = True
                
        if is_abort:
            # Clear state in PostgreSQL immediately
            await self.state_repo.clear_state(user_id)
            logger.info(f"🧹 [Conversational-Abort-Engine] Cleared active conversation state for user {user_id} upon trigger: {user_query}")
            
            response_text = "Ik heb de huidige setup-flow voor je geannuleerd. Je kunt me altijd vragen om iets nieuws te starten of een andere vraag stellen! 👍"
            state_reset = {"current_flow": "none", "slots": {}, "status": "none"}
            
            if actual_session_id:
                user_msg = ChatMessage(session_id=actual_session_id, role="user", content=user_query, created_at=datetime.utcnow(), intent=intent)
                assistant_msg = ChatMessage(session_id=actual_session_id, role="assistant", content=response_text, created_at=datetime.utcnow(), intent=intent)
                self.state_repo.session.add(user_msg)
                self.state_repo.session.add(assistant_msg)
                await self.state_repo.session.commit()

            return response_text, None, None, state_reset, None, ["Toon dashboard", "Start nieuwe setup"], actual_session_id
        
        # 1.5 Active Asset Priority Engine & Sequential Context Gathering
        explicit_symbol = None
        symbols_to_check = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX", "LINK"]
        for sym in symbols_to_check:
            if re.search(r'\b' + sym + r'\b', user_query, re.IGNORECASE):
                explicit_symbol = sym.upper()
                break
                
        page_symbol = None
        if context_data:
            if hasattr(context_data, "symbol"):
                page_symbol = getattr(context_data, "symbol", None)
            elif hasattr(context_data, "get"):
                page_symbol = context_data.get("symbol")
        
        start_db = time.perf_counter()
        
        if self.context_repo:
            db_context = await self.context_repo.load_runtime_context(user_id, page_symbol, explicit_symbol, intent)
            resolved_symbol = db_context["resolved_symbol"]
            live_data = db_context["live_data"]
            conv_state = db_context["conv_state"]
            context = db_context["context"]
            portfolio_intelligence = db_context["portfolio_intelligence"]
            behavioral_signals = db_context["behavioral_signals"]
            user = db_context["user"]
        else:
            conv_state = await self.state_repo.get_state(user_id)
            resolved_symbol = explicit_symbol or page_symbol or (conv_state.get("asset") if conv_state else None) or "BTC"
            live_data = await self.market_data_repo.get_latest_market_data(resolved_symbol)
            context = await self._build_context(user_id, intent)
            portfolio_intelligence = await self.bot_repo.get_portfolio_intelligence_context(user_id)
            behavioral_signals = await self.bot_repo.get_user_behavioral_signals(user_id)
            user = await self.user_repo.get_by_id(user_id)
        
        self.db_duration_ms = (time.perf_counter() - start_db) * 1000
        logger.info(f"⚡ [Ai-Assistant-Service] SEQUENTIAL DATABASE CONTEXT GATHER took {self.db_duration_ms:.2f}ms (Resolved Asset: {resolved_symbol})")
 
        # Deterministic slot pre-parsing (Hybrid AI + Confirm UX)
        conv_state = await self._deterministic_pre_parse_slots(user_query, conv_state, resolved_symbol, user_id)
        if conv_state and conv_state.get("status") == "complete":
            # Deterministically build final draft payload in Python
            draft = self._build_deterministic_draft(conv_state)
            await self.state_repo.clear_state(user_id)
            
            flow_word = conv_state.get("current_flow", "setup").split("_")[0]
            response_text = f"Perfect! Ik heb de {flow_word} voor {resolved_symbol} klaargezet. Bevestig de card hieronder om hem te activeren! 👍"
            state_reset = {"current_flow": "none", "slots": {}, "status": "none"}
            logger.info(f"🏁 [Deterministic-Completion-Interceptor] Completed flow '{conv_state.get('current_flow')}' with draft payload: {draft}")
            
            if actual_session_id:
                user_msg = ChatMessage(session_id=actual_session_id, role="user", content=user_query, created_at=datetime.utcnow(), intent=intent)
                assistant_msg = ChatMessage(session_id=actual_session_id, role="assistant", content=response_text, created_at=datetime.utcnow(), intent=intent, actions=draft)
                self.state_repo.session.add(user_msg)
                self.state_repo.session.add(assistant_msg)
                await self.state_repo.session.commit()

            return response_text, None, draft, state_reset, None, ["Activeer setup", "Vraag over macro"], actual_session_id
        # Process Live Market Context
        live_context = "No live market data available in database."
        if live_data:
            live_context = (
                f"CURRENT LIVE DATA (TRUTH):\n"
                f"Symbol: {resolved_symbol}\n"
                f"Price: ${live_data.price:,.2f}\n"
                f"24h Change: {live_data.change_24h}%\n"
                f"Last Updated: {live_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"INSTRUCTION: Use THIS price for any current price questions. Do NOT guess."
            )

        # Process current conversation state
        conv_state_str = "No active workflow state."
        if conv_state:
            import json
            conv_state_str = (
                f"ACTIVE WORKFLOW STATE:\n"
                f"Current Flow: {conv_state.get('current_flow')}\n"
                f"Asset: {conv_state.get('asset')}\n"
                f"Slots gathered so far: {json.dumps(conv_state.get('slots'))}"
            )

        # Format conversation history
        history_str = "No previous chat history."
        if history:
            history_lines = []
            for msg in history[-10:]:  # Last 10 messages for safety
                role = msg.get("role", "user")
                text = msg.get("text", "")
                history_lines.append(f"{role.upper()}: {text}")
            history_str = "\n".join(history_lines)

        # Build Portfolio Context
        portfolio_context_str = self._build_portfolio_context_str(portfolio_intelligence)

        # Route Agent (Select Role)
        role_key = self._route_role(intent)
        
        # Get User Preferences
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        user_name = user.first_name if (user and getattr(user, "first_name", None)) else "Handelaar"
        response_language = _response_language_name(preferences)

        # Assemble Adaptive Intelligence Profile
        stated_exp = preferences.get("experience_level", "beginner")
        adaptive_profile_str = _build_adaptive_profile_str(preferences, behavioral_signals, user_name)

        # 5. Build System Prompt
        system_role = get_role_prompt(role_key, preferences, intent=intent, user_name=user_name)
        self._active_preferences = preferences

        # 5.5 Synthesise Chronological Continuity and Event Memory Context
        continuity_str = await self._build_continuity_context_str(user_id)

        # 6. Generate Response via GATEWAY using JSON mode to allow action parameters
        prompt = (
            f"=== BOVENGESCHIKT TARGET ASSET MANDAAT (CRITICAL DIRECTIVE) ===\n"
            f"De actieve asset die hieronder wordt meegegeven is ALTIJD de primaire asset waarover je spreekt wanneer de gebruiker praat over 'deze asset', 'deze coin', 'dit gedrag' of 'hier':\n"
            f"PRIMARY TARGET ASSET: {resolved_symbol}\n"
            f"Negeer eventuele andere assets uit de conversatiegeschiedenis tenzij de gebruiker in zijn allerlaatste bericht expliciet een andere asset bij naam noemt.\n\n"
            f"USER QUERY: {user_query}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_str}\n\n"
            f"CONVERSATION STATE ENGINE:\n{conv_state_str}\n\n"
            f"LIVE MARKET CONTEXT:\n{live_context}\n\n"
            f"HISTORICAL/ANALYSIS CONTEXT:\n{context}\n\n"
            f"REAL-TIME PORTFOLIO CONTEXT:\n{portfolio_context_str}\n\n"
            f"CHRONOLOGICAL CONTINUITY & EVENT MEMORY:\n{continuity_str}\n\n"
            f"ADAPTIVE INTELLIGENCE CONTEXT:\n{adaptive_profile_str}\n\n"
            f"FRONTEND METADATA:\n{context_data}"
        )

        # Build registry prompt instructions dynamically from central flow registry
        registry_instructions = self._build_flow_registry_prompt(conv_state, stated_exp)

        system_role_json = (
            system_role + 
            "\n\nIMPORTANT: You must return a JSON object with exactly six fields:\n"
            f"- 'response': (string) your conversational response to the user's message in {response_language}.\n"
            "- 'action': (object or null) if the user explicitly asks to add or remove a coin to/from their watchlist, "
            "or open pages, populate this object. Otherwise, set 'action' to null.\n"
            "- 'draft': (object or null) if the user asks to create/generate/setup a DCA setup, trading setup, strategy, or bot, "
            "populate this object. Otherwise, set 'draft' to null.\n"
            "- 'state': (object or null) current active conversation workflow state.\n"
            "- 'reasoning': (object or null) internal diagnostic reasoning containing: "
            "'confidence_score' (float, 0-100), 'risk_detected' (boolean), 'reasons' (list of strings), and "
            "'coaching_level' (string, e.g. 'beginner' or 'advanced').\n"
            "- 'suggested_actions': (array of strings or null) 2-3 dynamic suggested next actions for the user, presented as brief phrases (e.g., ['Bekijk macro analyse voor SOL', 'Start DCA setup']).\n\n"
            f"{registry_instructions}\n"
            "=== ACTION SCHEMAS ===\n"
            "The 'action' object can represent a SINGLE action or a BUNDLE of multiple actions:\n"
            "1. For SINGLE actions, 'type' must be one of ['add_to_watchlist', 'remove_from_watchlist', 'open_setup_page', 'generate_strategy', 'open_bot_draft'], and 'symbol' and 'params' should be populated.\n"
            "2. For MULTIPLE actions, 'type' must be 'bundle'. Then, populate the 'actions' array.\n\n"
            "=== DRAFT SCHEMAS ===\n"
            "The 'draft' object represents a prefilled draft configured for the user to review. It must contain:\n"
            "- 'type': (string) 'setup', 'strategy', or 'bot'\n"
            "- 'payload': (object) matching the fields of the object:\n\n"
            "1. For 'setup' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL AI DCA'\n"
            "   * 'symbol': e.g., 'SOL'\n"
            "   * 'setup_type': 'dca' or 'trade'\n"
            "   * 'timeframe': '1W', '1D', or '4H' (default: '1W')\n"
            "   * 'dca_frequency': 'weekly', 'daily', or 'monthly' (required if setup_type is 'dca')\n"
            "   * 'dca_day': 'monday', 'tuesday', etc. (required if dca_frequency is 'weekly')\n"
            "   * 'min_macro_score': 0-100 (default: 30)\n"
            "   * 'max_macro_score': 0-100 (default: 70)\n"
            "   * 'min_technical_score': 0-100 (default: 40)\n"
            "   * 'max_technical_score': 0-100 (default: 80)\n"
            "   * 'min_market_score': 0-100 (default: 20)\n"
            "   * 'max_market_score': 0-100 (default: 60)\n\n"
            "2. For 'strategy' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL Breakout Strategy'\n"
            "   * 'symbol': 'SOL'\n"
            "   * 'setup_type': 'trade' or 'dca'\n"
            "   * 'execution_mode': 'fixed' or 'custom' (default: 'fixed')\n"
            "   * 'base_amount': float/int (default: 100.0)\n"
            "   * 'entry': float/int (required if setup_type is 'trade', e.g., 145.5)\n"
            "   * 'targets': array of floats (required if setup_type is 'trade', e.g., [160.0, 180.0])\n"
            "   * 'stop_loss': float/int (required if setup_type is 'trade', e.g., 135.0)\n\n"
            "3. For 'bot' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL Paper Bot'\n"
            "   * 'mode': 'manual', 'semi', or 'auto' (default: 'manual')\n"
            "   * 'is_live': boolean (false for paper, true for live, default: false)\n"
            "   * 'risk_profile': 'conservative', 'balanced', 'aggressive' (default: 'balanced')\n"
            "   * 'budget_total_eur': float/int (default: 500.0)\n"
            "   * 'budget_daily_limit_eur': float/int (default: 50.0)\n"
            "   * 'budget_min_order_eur': float/int (default: 10.0)\n"
            "   * 'budget_max_order_eur': float/int (default: 100.0)\n"
            "   * 'max_asset_exposure_pct': float/int (default: 100.0)\n"
            "   * 'cadence': 'daily' or 'weekly' (default: 'daily')\n"
            "   * 'base_currency': 'EUR' or 'USD' (default: 'EUR')\n"
        )

        schema = {
            "type": "object",
            "properties": {
                "response": {"type": "string"},
                "action": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["add_to_watchlist", "remove_from_watchlist", "open_setup_page", "generate_strategy", "open_bot_draft", "bundle"]},
                        "symbol": {"type": "string"},
                        "params": {"type": "object"},
                        "actions": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string", "enum": ["add_to_watchlist", "remove_from_watchlist", "open_setup_page", "generate_strategy", "open_bot_draft"]},
                                    "symbol": {"type": "string"},
                                    "params": {"type": "object"},
                                    "description": {"type": "string"}
                                },
                                "required": ["type"]
                            }
                        }
                    },
                    "required": ["type"],
                    "nullable": True
                },
                "draft": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["setup", "strategy", "bot"]},
                        "payload": {"type": "object"}
                    },
                    "required": ["type", "payload"],
                    "nullable": True
                },
                "state": {
                    "type": "object",
                    "properties": {
                        "current_flow": {"type": "string", "enum": ["setup_creation", "strategy_creation", "bot_creation", "none"]},
                        "asset": {"type": "string"},
                        "slots": {"type": "object"},
                        "missing_slots": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "status": {"type": "string", "enum": ["collecting", "complete", "none"]}
                    },
                    "required": ["current_flow", "slots", "status"],
                    "nullable": True
                },
                "reasoning": {
                    "type": "object",
                    "properties": {
                        "confidence_score": {"type": "number"},
                        "risk_detected": {"type": "boolean"},
                        "reasons": {
                            "type": "array",
                            "items": {"type": "string"}
                        },
                        "coaching_level": {"type": "string"}
                    },
                    "required": ["confidence_score", "risk_detected", "reasons", "coaching_level"],
                    "nullable": True
                },
                "suggested_actions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "nullable": True
                }
            },
        }

        response_data = await self.ai_gateway.ask(
            user_id=user_id, 
            prompt=prompt, 
            system_role=system_role_json, 
            mode="json",
            schema=schema,
            purpose=f"chat_{intent}",
            user_model=user
        )

        # Robust parsing of JSON-mode response
        chat_text = "⚠️ Kon geen analyse ophalen. Probeer opnieuw."
        action = None
        draft = None
        state = None
        reasoning = None
        suggested_actions = None

        if response_data:
            if isinstance(response_data, dict):
                chat_text = response_data.get("response", chat_text)
                action = response_data.get("action")
                draft = response_data.get("draft")
                state = response_data.get("state")
                reasoning = response_data.get("reasoning")
                suggested_actions = response_data.get("suggested_actions")
            elif isinstance(response_data, str):
                # Fallback if cached or raw string returned
                try:
                    import json
                    parsed = json.loads(response_data)
                    if isinstance(parsed, dict):
                        chat_text = parsed.get("response", chat_text)
                        action = parsed.get("action")
                        draft = parsed.get("draft")
                        state = parsed.get("state")
                        reasoning = parsed.get("reasoning")
                        suggested_actions = parsed.get("suggested_actions")
                    else:
                        chat_text = response_data
                except Exception:
                    chat_text = response_data

        # Ensure action/draft/state/reasoning are strictly dicts/None
        action = self._validate_and_sanitize_action(action)
        if not isinstance(draft, dict):
            draft = None
        if not isinstance(state, dict):
            state = None
        if not isinstance(reasoning, dict):
            reasoning = None
        if isinstance(suggested_actions, list):
            suggested_actions = [str(act) for act in suggested_actions if act]
        else:
            suggested_actions = None

        # Intercept and register transactional items as centralized pending actions / cards
        action, draft = await self._process_universal_action_cards(user_id, action, draft, trace_id)

        # ABSOLUTE BACKEND STATE SUPREMACY: If the backend has an active collecting flow,
        # we completely ignore the LLM's returned state and use our deterministic, persistent backend state.
        if conv_state and conv_state.get("status") == "collecting":
            state = conv_state
        else:
            # Otherwise, fall back to safe merging of slots
            if state and isinstance(state, dict) and conv_state and isinstance(conv_state, dict):
                state_slots = state.get("slots") or {}
                pre_slots = conv_state.get("slots") or {}
                for k, v in pre_slots.items():
                    if v is not None and v != "":
                        state_slots[k] = v
                state["slots"] = state_slots

        # Apply deterministic safety post-processing guardrail to text response
        chat_text = self._apply_safety_guardrails(chat_text)
        chat_text = self._apply_legacy_profile_overlay(
            chat_text,
            intent=intent,
            context_data=context_data,
            resolved_symbol=resolved_symbol,
        )

        # Manage DB conversation state transitions
        if state:
            status = state.get("status")
            current_flow = state.get("current_flow")
            if status == "collecting" and current_flow and current_flow != "none":
                # Save state to DB
                asset_val = state.get("asset") or state.get("slots", {}).get("symbol") or resolved_symbol
                await self.state_repo.save_state(user_id, current_flow, asset_val, state.get("slots", {}))
                draft = None  # Block partial drafts from executing
            elif status == "complete" or current_flow == "none":
                # Save onboarding slots to preferences if completed onboarding
                if current_flow == "user_onboarding":
                    onboarding_slots = state.get("slots", {}) or {}
                    prefs_update = {}
                    if "experience_level" in onboarding_slots:
                        prefs_update["experience_level"] = onboarding_slots["experience_level"]
                    if "risk_profile" in onboarding_slots:
                        prefs_update["risk_profile"] = onboarding_slots["risk_profile"]
                    if "investment_goals" in onboarding_slots:
                        prefs_update["investment_goals"] = onboarding_slots["investment_goals"]
                    if prefs_update:
                        await self.user_repo.update_ai_preferences(user_id, prefs_update)
                        logger.info(f"👤 Saved onboarding preferences in non-stream for user {user_id}: {prefs_update}")
                # Clear state from DB
                await self.state_repo.clear_state(user_id)
        else:
            await self.state_repo.clear_state(user_id)

        # Persist conversation message exchange to DB if session tracking is enabled
        if actual_session_id:
            user_msg = ChatMessage(
                session_id=actual_session_id,
                role="user",
                content=user_query,
                created_at=datetime.utcnow(),
                intent=intent
            )
            assistant_msg = ChatMessage(
                session_id=actual_session_id,
                role="assistant",
                content=chat_text,
                created_at=datetime.utcnow(),
                intent=intent,
                actions=action
            )
            self.state_repo.session.add(user_msg)
            self.state_repo.session.add(assistant_msg)
            
            # Update session updated_at timestamp to bubble to top of active list
            session_stmt = update(ChatSession).where(ChatSession.id == actual_session_id).values(updated_at=datetime.utcnow())
            await self.state_repo.session.execute(session_stmt)
            await self.state_repo.session.commit()

        return chat_text, action, draft, state, reasoning, suggested_actions, actual_session_id

    async def get_chat_response_stream(
        self, 
        user_id: int, 
        user_query: str, 
        history: Optional[List[Dict[str, Any]]] = None,
        context_data: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None,
        background_tasks: Optional[Any] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        🚀 Hardened Server-Sent Events (SSE) Chat Stream
        Streams conversational response tokens real-time, and yields final validated envelope data.
        """
        # Start response time tracking
        self.start_overall_time = time.perf_counter()
        import uuid
        self.trace_id = trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
        
        # 1. Classify Intent (Rule-based V1)
        intent = self._classify_intent(user_query)
        logger.info(f"🧠 Assistant Chat Intent: {intent} for streaming query: {user_query}")
        
        # 1.1 Conversational Abort/Reset Engine Interceptor (Bypasses DB gather and LLM calls entirely!)
        abort_triggers = ["stop", "annuleer", "annuleren", "laat maar", "reset", "opnieuw beginnen", "wis alles", "wis setup"]
        q_lower = user_query.strip().lower()
        import re
        q_clean = re.sub(r'[^\w\s]', '', q_lower)
        
        is_abort = False
        if any(trigger in q_clean for trigger in abort_triggers):
            # Exclude trading stop terms that contain 'stop'
            trading_stop_terms = ["stop-loss", "stop loss", "stoploss", "stop-limit", "stop limit", "stoplimit"]
            if any(term in q_lower for term in trading_stop_terms):
                is_abort = False
            else:
                is_abort = True

        if is_abort:
            # Clear state in PostgreSQL immediately
            await self.state_repo.clear_state(user_id)
            logger.info(f"🧹 [Conversational-Abort-Engine] Cleared active conversation state for user {user_id} upon trigger: {user_query}")
            
            abort_msg = "Ik heb de huidige setup-flow voor je geannuleerd. Je kunt me altijd vragen om iets nieuws te starten of een andere vraag stellen! 👍"
            
            # Log abort event (Fase 3: Runtime Observability & Analytics)
            try:
                duration_ms = int((time.perf_counter() - self.start_overall_time) * 1000)
                if background_tasks:
                    background_tasks.add_task(
                        record_ai_usage_background,
                        user_id=user_id,
                        user_query=user_query,
                        prompt="[ABORT_TRIGGER]",
                        chat_text=abort_msg,
                        intent=intent,
                        resolved_symbol="GLOBAL",
                        trace_id=self.trace_id,
                        duration_ms=duration_ms,
                        completion_status="aborted"
                    )
                else:
                    import asyncio
                    asyncio.create_task(
                        record_ai_usage_background(
                            user_id=user_id,
                            user_query=user_query,
                            prompt="[ABORT_TRIGGER]",
                            chat_text=abort_msg,
                            intent=intent,
                            resolved_symbol="GLOBAL",
                            trace_id=self.trace_id,
                            duration_ms=duration_ms,
                            completion_status="aborted"
                        )
                    )
            except Exception as le:
                logger.error(f"❌ Error logging abort event: {le}")

            yield {"event": "text", "data": abort_msg}
            yield {"event": "envelope", "data": {
                "response": abort_msg,
                "action": None,
                "draft": None,
                "state": {"current_flow": "none", "slots": {}, "status": "none"},
                "reasoning": None
            }}
            return
        
        # 1.5 Active Asset Priority Engine & Sequential Context Gathering
        explicit_symbol = None
        symbols_to_check = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX", "LINK"]
        for sym in symbols_to_check:
            if re.search(r'\b' + sym + r'\b', user_query, re.IGNORECASE):
                explicit_symbol = sym.upper()
                break
                
        page_symbol = None
        if context_data:
            if hasattr(context_data, "symbol"):
                page_symbol = getattr(context_data, "symbol", None)
            elif hasattr(context_data, "get"):
                page_symbol = context_data.get("symbol")
        
        start_db = time.perf_counter()
        
        if self.context_repo:
            db_context = await self.context_repo.load_runtime_context(user_id, page_symbol, explicit_symbol, intent)
            resolved_symbol = db_context["resolved_symbol"]
            live_data = db_context["live_data"]
            conv_state = db_context["conv_state"]
            context = db_context["context"]
            portfolio_intelligence = db_context["portfolio_intelligence"]
            behavioral_signals = db_context["behavioral_signals"]
            user = db_context["user"]
        else:
            conv_state = await self.state_repo.get_state(user_id)
            resolved_symbol = explicit_symbol or page_symbol or (conv_state.get("asset") if conv_state else None) or "BTC"
            live_data = await self.market_data_repo.get_latest_market_data(resolved_symbol)
            context = await self._build_context(user_id, intent)
            portfolio_intelligence = await self.bot_repo.get_portfolio_intelligence_context(user_id)
            behavioral_signals = await self.bot_repo.get_user_behavioral_signals(user_id)
            user = await self.user_repo.get_by_id(user_id)
        
        # Step 8: Finn Coach
        setup_service = SetupService(self.state_repo.session)
        active_setup_res = await setup_service.get_active_setup(user_id, resolved_symbol)
        active_setup = active_setup_res.get("active")
        
        coach_context_str = "No active setup for this asset."
        if active_setup:
            status_explanation = await setup_service.explain_setup_status(active_setup["setup_id"], user_id)
            import json
            coach_context_str = (
                f"FINN COACH CONTEXT (Current Setup Status):\n"
                f"Setup Name: {active_setup['name']}\n"
                f"Status: {status_explanation['status']}\n"
                f"Match Percentage: {status_explanation['match_percentage']}%\n"
                f"Reasons: {json.dumps(status_explanation['reasons'])}\n"
                f"Advice: {status_explanation['advice']}\n"
                f"Current Scores: {json.dumps(status_explanation['current_scores'])}\n"
            )
        
        self.db_duration_ms = (time.perf_counter() - start_db) * 1000
        logger.info(f"⚡ [Ai-Assistant-Service] SEQUENTIAL DATABASE CONTEXT GATHER (Stream) took {self.db_duration_ms:.2f}ms (Resolved Asset: {resolved_symbol})")

        # Deterministic slot pre-parsing (Hybrid AI + Confirm UX)
        conv_state = await self._deterministic_pre_parse_slots(user_query, conv_state, resolved_symbol, user_id)

        if conv_state and conv_state.get("status") == "complete":
            # Deterministically build final draft payload in Python
            draft = self._build_deterministic_draft(conv_state)
            await self.state_repo.clear_state(user_id)
            
            flow_word = conv_state.get("current_flow", "setup").split("_")[0]
            response_text = f"Perfect! Ik heb de {flow_word} voor {resolved_symbol} klaargezet. Bevestig de card hieronder om hem te activeren! 👍"
            state_reset = {"current_flow": "none", "slots": {}, "status": "none"}
            logger.info(f"🏁 [Deterministic-Completion-Interceptor] Completed flow '{conv_state.get('current_flow')}' with draft payload: {draft}")
            yield {"event": "text", "data": response_text}
            yield {"event": "envelope", "data": {
                "response": response_text,
                "action": None,
                "draft": draft,
                "state": state_reset,
                "reasoning": None
            }}
            return

        # Process Live Market Context
        live_context = "No live market data available in database."
        if live_data:
            live_context = (
                f"CURRENT LIVE DATA (TRUTH):\n"
                f"Symbol: {resolved_symbol}\n"
                f"Price: ${live_data.price:,.2f}\n"
                f"24h Change: {live_data.change_24h}%\n"
                f"Last Updated: {live_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"INSTRUCTION: Use THIS price for any current price questions. Do NOT guess."
            )

        # Process current conversation state
        conv_state_str = "No active workflow state."
        if conv_state:
            import json
            conv_state_str = (
                f"ACTIVE WORKFLOW STATE:\n"
                f"Current Flow: {conv_state.get('current_flow')}\n"
                f"Asset: {conv_state.get('asset')}\n"
                f"Slots gathered so far: {json.dumps(conv_state.get('slots'))}"
            )

        # Format conversation history
        history_str = "No previous chat history."
        if history:
            history_lines = []
            for msg in history[-10:]:  # Last 10 messages for safety
                role = msg.get("role", "user")
                text = msg.get("text", "")
                history_lines.append(f"{role.upper()}: {text}")
            history_str = "\n".join(history_lines)

        # Build Portfolio Context
        portfolio_context_str = await self._build_context(user_id, intent)
        # Route Agent (Select Role)
        role_key = self._route_role(intent)
        
        # Get User Preferences
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        user_name = user.first_name if (user and getattr(user, "first_name", None)) else "Handelaar"
        response_language = _response_language_name(preferences)

        # Assemble Adaptive Intelligence Profile
        stated_exp = preferences.get("experience_level", "beginner")
        adaptive_profile_str = _build_adaptive_profile_str(preferences, behavioral_signals, user_name)

        # 5. Build System Prompt
        system_role = get_role_prompt(role_key, preferences, intent=intent, user_name=user_name)
        self._active_preferences = preferences

        # 5.5 Synthesise Chronological Continuity and Event Memory Context
        continuity_str = await self._build_continuity_context_str(user_id)

        # 6. Generate Response via GATEWAY using JSON mode to allow action parameters
        prompt = (
            f"=== BOVENGESCHIKT TARGET ASSET MANDAAT (CRITICAL DIRECTIVE) ===\n"
            f"De actieve asset die hieronder wordt meegegeven is ALTIJD de primaire asset waarover je spreekt wanneer de gebruiker praat over 'deze asset', 'deze coin', 'dit gedrag' of 'hier':\n"
            f"PRIMARY TARGET ASSET: {resolved_symbol}\n"
            f"Negeer eventuele andere assets uit de conversatiegeschiedenis tenzij de gebruiker in his allerlaatste bericht expliciet een andere asset bij naam noemt.\n\n"
            f"USER QUERY: {user_query}\n\n"
            f"RECENT CONVERSATION HISTORY:\n{history_str}\n\n"
            f"CONVERSATION STATE ENGINE:\n{conv_state_str}\n\n"
            f"LIVE MARKET CONTEXT:\n{live_context}\n\n"
            f"HISTORICAL/ANALYSIS CONTEXT:\n{context}\n\n"
            f"REAL-TIME PORTFOLIO CONTEXT:\n{portfolio_context_str}\n\n"
            f"CHRONOLOGICAL CONTINUITY & EVENT MEMORY:\n{continuity_str}\n\n"
            f"ADAPTIVE INTELLIGENCE CONTEXT:\n{adaptive_profile_str}\n\n"
            f"FINN COACH CONTEXT:\n{coach_context_str}\n\n"
            f"FRONTEND METADATA:\n{context_data}"
        )

        # Build registry prompt instructions dynamically from central flow registry
        registry_instructions = self._build_flow_registry_prompt(conv_state, stated_exp)

        system_role_json = (
            system_role + 
            "\n\nIMPORTANT: You must return a JSON object with exactly six fields:\n"
            f"- 'response': (string) your conversational response to the user's message in {response_language}.\n"
            "- 'action': (object or null) if the user explicitly asks to add or remove a coin to/from their watchlist, "
            "or open pages, populate this object. Otherwise, set 'action' to null.\n"
            "- 'draft': (object or null) if the user asks to create/generate/setup a DCA setup, trading setup, strategy, or bot, "
            "populate this object. Otherwise, set 'draft' to null.\n"
            "- 'state': (object or null) current active conversation workflow state.\n"
            "- 'reasoning': (object or null) internal diagnostic reasoning containing: "
            "'confidence_score' (float, 0-100), 'risk_detected' (boolean), 'reasons' (list of strings), and "
            "'coaching_level' (string, e.g. 'beginner' or 'advanced').\n"
            "- 'suggested_actions': (array of strings or null) 2-3 dynamic suggested next actions for the user, presented as brief phrases (e.g., ['Bekijk macro analyse voor SOL', 'Start DCA setup']).\n\n"
            f"{registry_instructions}\n"
            "=== ACTION SCHEMAS ===\n"
            "The 'action' object can represent a SINGLE action or a BUNDLE of multiple actions:\n"
            "1. For SINGLE actions, 'type' must be one of ['add_to_watchlist', 'remove_from_watchlist', 'open_setup_page', 'generate_strategy', 'open_bot_draft', 'navigate_to_page'], and 'symbol' and 'params' should be populated.\n"
            "2. For 'navigate_to_page', you must specify 'params' with a 'path' key. ALLOWED_PATHS (strict whitelist): ['/dashboard', '/macro', '/technical', '/bot', '/strategy', '/setup', '/report', '/profile']. Any path outside this whitelist is strictly rejected.\n"
            "3. For MULTIPLE actions, 'type' must be 'bundle'. Then, populate the 'actions' array.\n\n"
            "=== DRAFT SCHEMAS ===\n"
            "The 'draft' object represents a prefilled draft configured for the user to review. It must contain:\n"
            "- 'type': (string) 'setup', 'strategy', or 'bot'\n"
            "- 'payload': (object) matching the fields of the object.\n"
            "IMPORTANT: Do not assume or hallucinate values for the draft that the user has not provided. If a value is unknown, set it to null. You must ask the user for missing fields instead of guessing. For example, if the user does not specify a frequency for DCA, do not guess 'weekly', but leave it null and ask the user.\n\n"
            "1. For 'setup' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL AI DCA'\n"
            "   * 'symbol': e.g., 'SOL'\n"
            "   * 'setup_type': 'dca' or 'trade'\n"
            "   * 'timeframe': '1W', '1D', or '4H' (default: '1W')\n"
            "   * 'dca_frequency': 'weekly', 'daily', or 'monthly' (required if setup_type is 'dca')\n"
            "   * 'dca_day': 'monday', 'tuesday', etc. (required if dca_frequency is 'weekly')\n"
            "   * 'min_macro_score': 0-100 (default: 30)\n"
            "   * 'max_macro_score': 0-100 (default: 70)\n"
            "   * 'min_technical_score': 0-100 (default: 40)\n"
            "   * 'max_technical_score': 0-100 (default: 80)\n"
            "   * 'min_market_score': 0-100 (default: 20)\n"
            "   * 'max_market_score': 0-100 (default: 60)\n\n"
            "2. For 'strategy' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL Breakout Strategy'\n"
            "   * 'symbol': 'SOL'\n"
            "   * 'setup_type': 'trade' or 'dca'\n"
            "   * 'execution_mode': 'fixed' or 'custom' (default: 'fixed')\n"
            "   * 'base_amount': float/int (default: 100.0)\n"
            "   * 'entry': float/int (required if setup_type is 'trade', e.g., 145.5)\n"
            "   * 'targets': array of floats (required if setup_type is 'trade', e.g., [160.0, 180.0])\n"
            "   * 'stop_loss': float/int (required if setup_type is 'trade', e.g., 135.0)\n\n"
            "3. For 'bot' drafts:\n"
            "   * 'name': descriptive name, e.g., 'SOL Paper Bot'\n"
            "   * 'mode': 'manual', 'semi', or 'auto' (default: 'manual')\n"
            "   * 'is_live': boolean (false for paper, true for live, default: false)\n"
            "   * 'risk_profile': 'conservative', 'balanced', 'aggressive' (default: 'balanced')\n"
            "   * 'budget_total_eur': float/int (default: 500.0)\n"
            "   * 'budget_daily_limit_eur': float/int (default: 50.0)\n"
            "   * 'budget_min_order_eur': float/int (default: 10.0)\n"
            "   * 'budget_max_order_eur': float/int (default: 100.0)\n"
            "   * 'max_asset_exposure_pct': float/int (default: 100.0)\n"
            "   * 'cadence': 'daily' or 'weekly' (default: 'daily')\n"
            "   * 'base_currency': 'EUR' or 'USD' (default: 'EUR')\n"
        )

        from backend.utils.openai_streaming import stream_gpt_json_response
        
        envelope = None
        
        # Start streaming OpenAI and parsing
        async for chunk in stream_gpt_json_response(prompt, system_role_json):
            if chunk["event"] == "text":
                yield chunk
            elif chunk["event"] == "envelope":
                envelope = chunk["data"]

        # Robust parsing of finalized JSON envelope
        chat_text = "⚠️ Kon geen analyse ophalen. Probeer opnieuw."
        action = None
        draft = None
        state = None
        reasoning = None
        suggested_actions = None

        if envelope:
            chat_text = envelope.get("response", chat_text)
            action = envelope.get("action")
            draft = envelope.get("draft")
            state = envelope.get("state")
            reasoning = envelope.get("reasoning")
            suggested_actions = envelope.get("suggested_actions")

        # Ensure types are strict and validate actions
        action = self._validate_and_sanitize_action(action)
        if not isinstance(draft, dict): draft = None
        if not isinstance(state, dict): state = None
        if not isinstance(reasoning, dict): reasoning = None
        if isinstance(suggested_actions, list):
            suggested_actions = [str(act) for act in suggested_actions if act]
        else:
            suggested_actions = None

        # Intercept and register transactional items as centralized pending actions / cards
        action, draft = await self._process_universal_action_cards(user_id, action, draft, self.trace_id)

        # ABSOLUTE BACKEND STATE SUPREMACY: If the backend has an active collecting flow,
        # we completely ignore the LLM's returned state and use our deterministic, persistent backend state.
        if conv_state and conv_state.get("status") == "collecting":
            state = conv_state
        else:
            # Otherwise, fall back to safe merging of slots
            if state and isinstance(state, dict) and conv_state and isinstance(conv_state, dict):
                state_slots = state.get("slots") or {}
                pre_slots = conv_state.get("slots") or {}
                for k, v in pre_slots.items():
                    if v is not None and v != "":
                        state_slots[k] = v
                state["slots"] = state_slots

        # Apply safety guardrails to streamed text
        chat_text = self._apply_safety_guardrails(chat_text)
        chat_text = self._apply_legacy_profile_overlay(
            chat_text,
            intent=intent,
            context_data=context_data,
            resolved_symbol=resolved_symbol,
        )

        # Manage DB conversation state transitions
        if state:
            status = state.get("status")
            current_flow = state.get("current_flow")
            if status == "collecting" and current_flow and current_flow != "none":
                # Save state to DB
                asset_val = state.get("asset") or state.get("slots", {}).get("symbol") or resolved_symbol
                await self.state_repo.save_state(user_id, current_flow, asset_val, state.get("slots", {}))
                draft = None  # Block partial drafts from executing
            elif status == "complete" or current_flow == "none":
                # Save onboarding slots to preferences if completed onboarding
                if current_flow == "user_onboarding":
                    onboarding_slots = state.get("slots", {}) or {}
                    prefs_update = {}
                    if "experience_level" in onboarding_slots:
                        prefs_update["experience_level"] = onboarding_slots["experience_level"]
                    if "risk_profile" in onboarding_slots:
                        prefs_update["risk_profile"] = onboarding_slots["risk_profile"]
                    if "investment_goals" in onboarding_slots:
                        prefs_update["investment_goals"] = onboarding_slots["investment_goals"]
                    if prefs_update:
                        await self.user_repo.update_ai_preferences(user_id, prefs_update)
                        logger.info(f"👤 Saved onboarding preferences in stream for user {user_id}: {prefs_update}")
                # Clear state from DB
                await self.state_repo.clear_state(user_id)
        else:
            await self.state_repo.clear_state(user_id)

        # 7. Selective Preference Update (Optional/Explicit feedback)
        await self._handle_implicit_feedback(user_id, user_query)

        # 8. Runtime Observability & Analytics (Fase 3)
        try:
            parser_recovery_triggered = envelope.get("parser_recovery_triggered", False) if envelope else False
            confidence_score = reasoning.get("confidence_score") if reasoning else None
            safety_guardrail_triggered = (chat_text != envelope.get("response")) if (envelope and chat_text) else False
            duration_ms = int((time.perf_counter() - self.start_overall_time) * 1000)
            
            if background_tasks:
                background_tasks.add_task(
                    record_ai_usage_background,
                    user_id=user_id,
                    user_query=user_query,
                    prompt=prompt,
                    chat_text=chat_text,
                    intent=intent,
                    resolved_symbol=resolved_symbol,
                    trace_id=self.trace_id,
                    duration_ms=duration_ms,
                    confidence_score=confidence_score,
                    parser_recovery_triggered=parser_recovery_triggered,
                    safety_guardrail_triggered=safety_guardrail_triggered,
                    completion_status="success"
                )
                logger.info(f"📊 [Ai-Assistant-Service] Scheduled background task logging for trace {self.trace_id}")
            else:
                # Fire and forget locally using python asyncio task queue
                import asyncio
                asyncio.create_task(
                    record_ai_usage_background(
                        user_id=user_id,
                        user_query=user_query,
                        prompt=prompt,
                        chat_text=chat_text,
                        intent=intent,
                        resolved_symbol=resolved_symbol,
                        trace_id=self.trace_id,
                        duration_ms=duration_ms,
                        confidence_score=confidence_score,
                        parser_recovery_triggered=parser_recovery_triggered,
                        safety_guardrail_triggered=safety_guardrail_triggered,
                        completion_status="success"
                    )
                )
                logger.info(f"📊 [Ai-Assistant-Service] Scheduled asyncio Task queue logging for trace {self.trace_id}")
        except Exception as ue:
            logger.error(f"❌ Error recording streaming usage analytics: {ue}")

        # Log total duration
        overall_duration_ms = (time.perf_counter() - self.start_overall_time) * 1000
        logger.info(
            f"⏱️ [Ai-Assistant-Service] TOTAL get_chat_response_stream execution completed in {overall_duration_ms:.2f}ms"
        )

        # Yield the finalized, fully polished envelope object
        yield {
            "event": "envelope",
            "data": {
                "response": chat_text,
                "action": action,
                "draft": draft,
                "state": state,
                "reasoning": reasoning,
                "suggested_actions": suggested_actions
            }
        }

    def _apply_safety_guardrails(self, response_text: str) -> str:
        """
        🛡️ Deterministic Safety Guardrail (Post-Processing)
        Enforces read-only portfolio intelligence constraints and prevents the AI from giving hard buy/sell advice.
        """
        # Hard transaction patterns to detect and flag or soften
        unauthorized_phrases = [
            (r'\b(koop nu|buy now|verkoop nu|sell now)\b', "overweeg de setup"),
            (r'\b(je moet kopen|you must buy|je moet verkopen|you must sell)\b', "kan een setup overwogen worden"),
            (r'\b(adviseer ik te kopen|adviseer ik om te kopen|adviseer ik te verkopen)\b', "is een mogelijkheid volgens de indicators"),
            (r'\b(direct kopen|direct verkopen)\b', "een setup in te richten")
        ]
        
        import re
        softened_text = response_text
        for pattern, replacement in unauthorized_phrases:
            softened_text = re.sub(pattern, replacement, softened_text, flags=re.IGNORECASE)
            
        # Add a gentle read-only footer disclaimer if any strong trigger words or allocations are discussed, or as a general assistant best practice.
        # Disabled to keep conversational flow clean and premium.
        pass
            
        return softened_text

    def _legacy_general_profile_line(
        self,
        context_data: Optional[Dict[str, Any]],
        resolved_symbol: Optional[str] = None,
    ) -> str:
        payload = context_data or {}
        if not payload.get("trader_profile_used"):
            return ""

        profile = payload.get("trader_profile") if isinstance(payload.get("trader_profile"), dict) else {}
        trader_types = set(profile.get("trader_types") or [])
        risk_profiles = set(profile.get("risk_profiles") or [])
        behavior_flags = set(profile.get("behavior_flags") or [])
        asset_label = resolved_symbol or payload.get("symbol") or payload.get("asset") or "dit asset"

        if payload.get("profile_conflict_detected"):
            return (
                f"Voor jouw profiel geldt nu: deze vraag wijkt af van je normale stijl rond {asset_label}, "
                "dus toets eerst of je hier bewust van je eigen plan afwijkt."
            )
        if "fomo" in behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: wacht bij {asset_label} eerst op bevestiging "
                "en laat haast of fear of missing out je timing niet overnemen."
            )
        if "overtrades" in behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: voeg rond {asset_label} alleen iets toe "
                "als dit aantoonbaar beter is dan je laatste actie."
            )
        if {"takes_profit_too_early", "holds_losers_too_long"} <= behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: leg voor {asset_label} vooraf je exitplan vast "
                "en bewaak je invalidatie strakker, zodat je winnaars niet te vroeg afsnijdt "
                "en verliezers niet te lang laat rekken."
            )
        if "holds_losers_too_long" in behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: bewaak bij {asset_label} eerst je invalidatie, "
                "zodat je verliezers niet langer laat rekken dan je plan toelaat."
            )
        if "takes_profit_too_early" in behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: leg voor {asset_label} vooraf je exitplan vast, "
                "zodat je winnaars niet te vroeg afsnijdt."
            )
        if "leverage_seeking" in behavior_flags:
            return (
                f"Voor jouw profiel geldt nu: houd {asset_label} eerst zo simpel mogelijk "
                "en gebruik leverage niet als versneller van twijfel."
            )
        if "swing_trader" in trader_types:
            return f"Voor jouw profiel geldt nu: laat {asset_label} vooral tellen als 4H/Daily bevestiging terugkomt."
        if trader_types & {"investor", "dca_investor"}:
            return f"Voor jouw profiel geldt nu: forceer bij {asset_label} geen korte-termijn timing als je langetermijnplan niet echt verandert."
        if trader_types & {"day_trader", "scalper"}:
            return f"Voor jouw profiel geldt nu: behandel {asset_label} vooral als timing- en momentumvraag, niet als iets om blind te forceren."
        if "conservative" in risk_profiles:
            return f"Voor jouw profiel geldt nu: houd {asset_label} klein en selectief tot de sterkste twijfel weg is."
        return ""

    def _apply_legacy_profile_overlay(
        self,
        response_text: str,
        *,
        intent: str,
        context_data: Optional[Dict[str, Any]],
        resolved_symbol: Optional[str] = None,
    ) -> str:
        if intent not in {"general", "chat", "general_help", "product_help", "analysis", "report", "coach"}:
            return response_text
        profile_line = self._legacy_general_profile_line(context_data, resolved_symbol)
        if not profile_line:
            return response_text
        normalized = str(response_text or "").strip()
        if not normalized:
            return profile_line
        if profile_line.lower() in normalized.lower():
            return normalized
        if "voor jouw profiel" in normalized.lower():
            return normalized
        return f"{normalized}\n\n{profile_line}"

    async def _deterministic_pre_parse_slots(self, user_query: str, conv_state: Optional[dict], resolved_symbol: str, user_id: int) -> Optional[dict]:
        """
        🎯 Deterministic Slot Pre-Parser (Fase 2: Hybrid AI + Confirm UX)
        Extracts slot values deterministically before calling GPT to eliminate any LLM uncertainty.
        Allows users to specify any slot in any order with immediate asynchronous PostgreSQL persistence.
        """
        q_lower = user_query.strip().lower()
        
        # 1. Pre-initialize active flow if user requests to start one and there is no active flow
        if not conv_state or not conv_state.get("current_flow") or conv_state.get("current_flow") == "none":
            if any(w in q_lower for w in ["maak setup", "start setup", "setup voor", "setup aanmaken", "nieuwe setup", "setup maken"]):
                conv_state = {
                    "current_flow": "setup_creation",
                    "slots": {"symbol": resolved_symbol},
                    "status": "collecting"
                }
                # PERSIST INITIALIZATION STATE TO DB IMMEDIATELY
                await self.state_repo.save_state(user_id, "setup_creation", resolved_symbol, conv_state["slots"])
                logger.info(f"🎯 [Deterministic-Pre-Parser] Persisted newly initialized setup flow to DB for user {user_id}")
            elif any(w in q_lower for w in ["maak strategie", "start strategie", "strategie voor", "nieuwe strategie", "strategie maken"]):
                # CHECK SETUP DEPENDENCY
                existing_setups = await self.setup_repo.get_all_setups(user_id)
                symbol_setups = [s for s in existing_setups if s.get("symbol") == resolved_symbol]
                
                if not symbol_setups:
                    # Redirect to setup_creation!
                    conv_state = {
                        "current_flow": "setup_creation",
                        "slots": {"symbol": resolved_symbol},
                        "status": "collecting",
                        "redirect_reason": "no_setup"
                    }
                    await self.state_repo.save_state(user_id, "setup_creation", resolved_symbol, conv_state["slots"])
                    logger.info(f"🎯 [Chain-of-Dependence] No setup found for {resolved_symbol}. Redirected user {user_id} to setup_creation.")
                else:
                    conv_state = {
                        "current_flow": "strategy_creation",
                        "slots": {
                            "symbol": resolved_symbol,
                            "setup_id": symbol_setups[0]["id"],
                            "setup_type": symbol_setups[0].get("setup_type", "trade")
                        },
                        "status": "collecting"
                    }
                    await self.state_repo.save_state(user_id, "strategy_creation", resolved_symbol, conv_state["slots"])
                    logger.info(f"🎯 [Chain-of-Dependence] Setup found with ID {symbol_setups[0]['id']} for {resolved_symbol}. Initialized strategy_creation for user {user_id}.")
            elif any(w in q_lower for w in ["maak bot", "start bot", "bot voor", "nieuwe bot", "bot maken"]):
                # CHECK STRATEGY DEPENDENCY
                existing_strategies = await self.strategy_repo.query_strategies(user_id, {"symbol": resolved_symbol})
                
                if not existing_strategies:
                    # Check if we have a setup for this symbol:
                    existing_setups = await self.setup_repo.get_all_setups(user_id)
                    symbol_setups = [s for s in existing_setups if s.get("symbol") == resolved_symbol]
                    
                    if symbol_setups:
                        # Setup exists but no strategy! Redirect to strategy_creation!
                        conv_state = {
                            "current_flow": "strategy_creation",
                            "slots": {
                                "symbol": resolved_symbol,
                                "setup_id": symbol_setups[0]["id"],
                                "setup_type": symbol_setups[0].get("setup_type", "trade")
                            },
                            "status": "collecting",
                            "redirect_reason": "no_strategy"
                        }
                        await self.state_repo.save_state(user_id, "strategy_creation", resolved_symbol, conv_state["slots"])
                        logger.info(f"🎯 [Chain-of-Dependence] Setup found but no strategy. Redirected user {user_id} to strategy_creation.")
                    else:
                        # Neither exists! Redirect to setup_creation!
                        conv_state = {
                            "current_flow": "setup_creation",
                            "slots": {"symbol": resolved_symbol},
                            "status": "collecting",
                            "redirect_reason": "no_setup_nor_strategy"
                        }
                        await self.state_repo.save_state(user_id, "setup_creation", resolved_symbol, conv_state["slots"])
                        logger.info(f"🎯 [Chain-of-Dependence] No setup/strategy found. Redirected user {user_id} to setup_creation.")
                else:
                    # We have a strategy! We can link its ID
                    conv_state = {
                        "current_flow": "bot_creation",
                        "slots": {
                            "name": f"{resolved_symbol} Bot",
                            "strategy_id": existing_strategies[0]["id"]
                        },
                        "status": "collecting"
                    }
                    await self.state_repo.save_state(user_id, "bot_creation", resolved_symbol, conv_state["slots"])
                    logger.info(f"🎯 [Chain-of-Dependence] Strategy found with ID {existing_strategies[0]['id']}. Initialized bot_creation for user {user_id}.")
                
        if not conv_state or not conv_state.get("current_flow") or conv_state.get("current_flow") == "none":
            return conv_state

        flow_name = conv_state.get("current_flow")
        slots = dict(conv_state.get("slots" or {})) if conv_state.get("slots") else {}
        
        # Ensure slots has at least symbol if applicable
        if "symbol" not in slots and flow_name in ["setup_creation", "strategy_creation"]:
            slots["symbol"] = resolved_symbol

        import re

        # Helper to extract numbers
        def extract_numbers(s: str) -> list:
            # Matches integers or floats
            return [float(x) for x in re.findall(r'\b\d+(?:\.\d+)?\b', s)]

        # Let's find the current missing slots in sequence to know what slot we are pre-parsing
        from backend.ai_agents.flow_registry import FLOW_DEFINITIONS
        flow = FLOW_DEFINITIONS.get(flow_name)
        if not flow:
            return conv_state

        # Check for immediate finalization override ("maak de setup", "finaliseer")
        is_explicit_finalize = any(w in q_lower for w in ["maak de setup", "maak nu", "opslaan", "finaliseer", "bevestig", "approve", "akkoord", "bevestig setup"])
        if is_explicit_finalize:
            conv_state["status"] = "complete"
            logger.info(f"🏁 [Deterministic-Pre-Parser] Forced completion for flow '{flow_name}' upon request: {user_query}")
            return conv_state

        updated = False

        # Unconditional slot updating (allows toggling selections / chip clicks!)
        if any(w in q_lower for w in ["trade", "actief", "actieve", "manual", "handmatig"]):
            slots["setup_type"] = "trade"
            updated = True
        elif any(w in q_lower for w in ["dca", "periodiek", "passief", "bijkopen"]):
            slots["setup_type"] = "dca"
            updated = True

        if any(w in q_lower for w in ["dagelijks", "daily", "dag"]):
            slots["dca_frequency"] = "daily"
            updated = True
        elif any(w in q_lower for w in ["wekelijks", "weekly", "week"]):
            slots["dca_frequency"] = "weekly"
            updated = True
        elif any(w in q_lower for w in ["maandelijks", "monthly", "maand"]):
            slots["dca_frequency"] = "monthly"
            updated = True

        # Base Amount
        # Look for eur inleg, e.g. "€100", "100 eur", "inleg van 100", "inleg: 100", "inleg 100"
        nums = extract_numbers(q_lower)
        if nums and any(w in q_lower for w in ["€", "eur", "inleg", "bedrag", "euro", "order", "inleg:"]):
            slots["base_amount"] = nums[0]
            updated = True

        # Entry Price
        if any(w in q_lower for w in ["instappen", "entry", "instap"]):
            nums = extract_numbers(q_lower)
            if nums:
                slots["entry"] = nums[0]
                updated = True

        # Take Profit Targets
        if any(w in q_lower for w in ["target", "winstdoel", "take profit", "targets"]):
            nums = extract_numbers(q_lower)
            if nums:
                slots["targets"] = nums
                updated = True

        # Stop Loss
        if any(w in q_lower for w in ["stop-loss", "stop loss", "stoploss"]):
            nums = extract_numbers(q_lower)
            if nums:
                slots["stop_loss"] = nums[0]
                updated = True

        # Experience Level
        if "beginner" in q_lower:
            slots["experience_level"] = "beginner"
            updated = True
        elif any(w in q_lower for w in ["intermediate", "gemiddeld", "midden"]):
            slots["experience_level"] = "intermediate"
            updated = True
        elif any(w in q_lower for w in ["advanced", "gevorderd", "ervaren", "expert"]):
            slots["experience_level"] = "advanced"
            updated = True

        # Risk Profile
        if any(w in q_lower for w in ["conservative", "voorzichtig", "laag"]):
            slots["risk_profile"] = "conservative"
            updated = True
        elif any(w in q_lower for w in ["balanced", "neutraal", "balans", "gemiddeld"]):
            slots["risk_profile"] = "balanced"
            updated = True
        elif any(w in q_lower for w in ["aggressive", "agressief", "hoog"]):
            slots["risk_profile"] = "aggressive"
            updated = True

        # Market Condition
        if any(w in q_lower for w in ["extreme fear", "extreme angst", "fear", "angst"]):
            slots["market_condition"] = "extreme_fear"
            updated = True
        elif any(w in q_lower for w in ["bull market", "bull", "stijgend", "stijgende"]):
            slots["market_condition"] = "bull_market"
            updated = True
        elif any(w in q_lower for w in ["bear market", "bear", "dalend", "dalende"]):
            slots["market_condition"] = "bear_market"
            updated = True
        elif any(w in q_lower for w in ["neutral", "neutraal", "zijwaarts"]):
            slots["market_condition"] = "neutral"
            updated = True

        # Budget Daily Limit
        if any(w in q_lower for w in ["dagelijks limiet", "daily limit", "daglimiet", "dagelijks"]):
            nums = extract_numbers(q_lower)
            if nums:
                slots["budget_daily_limit_eur"] = nums[0]
                updated = True

        # Name (for setup_creation or bot_creation)
        if "name" not in slots or slots.get("name") is None or slots.get("name") == "":
            # 1. Check for explicit name pattern (e.g., "genaamd SOL Power", "naam: Power")
            explicit_name = None
            import re
            name_match = re.search(r'(?:genaamd|naam:|heet|called)\s+([a-zA-Z0-9\s_-]{2,30})', user_query, re.IGNORECASE)
            if name_match:
                explicit_name = name_match.group(1).strip()
            
            # 2. Check if we should greedily capture the query as the name
            should_greedy_capture = False
            is_trigger = any(w in q_lower for w in ["maak setup", "setup voor", "maak bot", "start bot", "annuleer", "cancel", "edit", "approve", "akkoord"])
            is_slot_keyword = any(w in q_lower for w in ["trade", "dca", "dagelijks", "wekelijks", "maandelijks", "extreme fear", "bull market", "bear market", "neutraal"])
            
            if not is_trigger and not is_slot_keyword and 2 < len(user_query.strip()) < 40:
                if flow_name == "setup_creation":
                    # Only capture as name if we already have setup_type and market_condition!
                    if "setup_type" in slots and "market_condition" in slots:
                        should_greedy_capture = True
                elif flow_name == "bot_creation":
                    # For bot creation, name is the first question. Capture it!
                    should_greedy_capture = True

            if explicit_name:
                slots["name"] = explicit_name
                updated = True
            elif should_greedy_capture:
                slots["name"] = user_query.strip()
                updated = True

        if updated:
            conv_state["slots"] = slots
            logger.info(f"🎯 [Deterministic-Pre-Parser] Successfully updated slots: {slots}")

            # Re-check if any missing slots remain
            final_missing = []
            for step in flow.get("question_sequence", []):
                slot_key = step["slot"]
                if flow_name == "setup_creation" and slot_key == "dca_frequency" and slots.get("setup_type") != "dca":
                    continue
                if flow_name == "strategy_creation" and slot_key in ["entry", "targets", "stop_loss"] and slots.get("setup_type") != "trade":
                    continue

                if slot_key not in slots or slots[slot_key] is None or slots[slot_key] == "":
                    final_missing.append(slot_key)

            if not final_missing and is_explicit_finalize:
                conv_state["status"] = "complete"
                logger.info(f"🏁 [Deterministic-Pre-Parser] Flow '{flow_name}' completed on explicit request.")

            # PERSIST TO DATABASE IMMEDIATELY (prevents any loss from LLM confusion or status mismatch)
            asset_val = slots.get("symbol") or resolved_symbol
            await self.state_repo.save_state(user_id, flow_name, asset_val, slots)
            logger.info(f"🎯 [Deterministic-Pre-Parser] Saved updated slots to DB for user {user_id}: {slots}")

        return conv_state

    def _build_deterministic_draft(self, conv_state: dict) -> dict:
        """
        🎯 Builds the production-ready Draft object deterministically from conversation slots.
        """
        flow_name = conv_state.get("current_flow")
        slots = conv_state.get("slots") or {}
        symbol = slots.get("symbol", "BTC")

        if flow_name == "setup_creation":
            payload = {
                "name": slots.get("name") or f"{symbol} Setup",
                "symbol": symbol,
                "setup_type": slots.get("setup_type", "trade"),
                "timeframe": "1W",
                "market_condition": slots.get("market_condition", "extreme_fear")
            }
            if slots.get("setup_type") == "dca":
                payload["dca_frequency"] = slots.get("dca_frequency", "weekly")
                payload["dca_day"] = "monday"
                payload["min_macro_score"] = 30
                payload["max_macro_score"] = 70
                payload["min_technical_score"] = 40
                payload["max_technical_score"] = 80
                payload["min_market_score"] = 20
                payload["max_market_score"] = 60
            return {
                "type": "setup",
                "payload": payload
            }

        elif flow_name == "strategy_creation":
            payload = {
                "name": f"{symbol} Strategy",
                "symbol": symbol,
                "setup_type": slots.get("setup_type", "trade"),
                "execution_mode": "fixed",
                "risk_profile": slots.get("risk_profile", "balanced"),
                "base_amount": slots.get("base_amount", 100.0)
            }
            if slots.get("setup_type") == "trade":
                payload["entry"] = slots.get("entry", 100.0)
                payload["targets"] = slots.get("targets", [110.0, 120.0])
                payload["stop_loss"] = slots.get("stop_loss", 90.0)
            elif slots.get("setup_type") == "dca":
                payload["dca_mode"] = slots.get("dca_mode", "standard")
                if slots.get("dca_mode") == "custom":
                    payload["buy_score_threshold"] = slots.get("buy_score_threshold", 30.0)
            return {
                "type": "strategy",
                "payload": payload
            }

        elif flow_name == "bot_creation":
            payload = {
                "name": slots.get("name") or f"{symbol} Bot",
                "mode": slots.get("mode", "manual"),
                "is_live": slots.get("is_live", False),
                "risk_profile": slots.get("risk_profile", "balanced"),
                "budget_total_eur": slots.get("budget_total_eur", 500.0),
                "budget_daily_limit_eur": slots.get("budget_daily_limit_eur", 50.0),
                "budget_min_order_eur": slots.get("budget_min_order_eur", 10.0),
                "budget_max_order_eur": slots.get("budget_max_order_eur", 100.0),
                "max_asset_exposure_pct": slots.get("max_asset_exposure_pct", 100.0),
                "cadence": slots.get("cadence", "daily"),
                "base_currency": slots.get("base_currency", "EUR")
            }
            return {
                "type": "bot",
                "payload": payload
            }

        return {}


    def _validate_and_sanitize_action(self, action: Optional[dict]) -> Optional[dict]:
        """
        🛡️ Server-Side Action Path Whitelist Sanitization (Navigator Hardening)
        Ensures that navigate_to_page actions only target whitelisted application routes.
        """
        if not action or not isinstance(action, dict):
            return None
            
        ALLOWED_PATHS = [
            "/dashboard",
            "/macro",
            "/technical",
            "/bot",
            "/strategy",
            "/setup",
            "/report",
            "/profile"
        ]
        
        act_type = action.get("type")
        if act_type == "navigate_to_page":
            params = action.get("params") or {}
            path = params.get("path")
            if not path or not isinstance(path, str):
                logger.warning("⚠️ navigate_to_page missing path parameter. Rejecting action.")
                return None
                
            # Strip query parameters for base path comparison
            base_path = path.split("?")[0]
            if base_path not in ALLOWED_PATHS:
                logger.warning(f"🚨 Rejected unauthorized navigate_to_page route attempt: {path}")
                return None
                
        elif act_type == "bundle":
            sub_actions = action.get("actions") or []
            sanitized_subs = []
            for sub in sub_actions:
                sub_san = self._validate_and_sanitize_action(sub)
                if sub_san:
                    sanitized_subs.append(sub_san)
            if not sanitized_subs:
                return None
            action["actions"] = sanitized_subs
            
        return action


    async def _process_universal_action_cards(
        self, 
        user_id: int, 
        action: Optional[dict], 
        draft: Optional[dict], 
        trace_id: str
    ) -> tuple[Optional[dict], Optional[dict]]:
        """
        Intercepts transactional actions or drafts and registers them centrally as pending actions in the database,
        returning a standardized, unified Universal Action Card payload for the clients.
        """
        from backend.services.ai_action_engine import AiActionEngine
        action_engine = AiActionEngine(self.state_repo.session)

        processed_draft = draft
        processed_action = action

        # 1. Process Draft Payloads (setup, strategy, bot)
        if draft and isinstance(draft, dict):
            draft_type = draft.get("type")
            payload = draft.get("payload") or {}
            
            if draft_type in ["setup", "strategy", "bot"] and payload:
                # Register the transaction centrally on the server
                action_id = await action_engine.register_pending_action(
                    user_id=user_id,
                    action_type=f"{draft_type}_draft",
                    payload=payload,
                    trace_id=trace_id
                )
                
                # Replace with standardized Universal Action Card manifest payload
                processed_draft = {
                    "type": "action_card",
                    "card_type": f"{draft_type}_draft_card",
                    "action_id": action_id,
                    "payload": {
                        "name": payload.get("name") or f"{payload.get('symbol', 'Asset')} Draft",
                        "symbol": payload.get("symbol"),
                        "description": f"Goedgekeurd door AI. Bevestig om deze {draft_type} setup te activeren."
                    }
                }

        # 2. Process Transactional Actions (watchlist, deletion, risk profile modifications, etc.)
        if action and isinstance(action, dict):
            act_type = action.get("type")
            
            transactional_types = [
                "add_to_watchlist", "remove_from_watchlist", 
                "delete_bot", "stop_bot", "risk_profile_change"
            ]
            
            if act_type in transactional_types:
                # Extract payload parameters
                payload = action.get("params") or action.get("payload") or {}
                if not payload and action.get("symbol"):
                    payload = {"symbol": action["symbol"]}

                # Register the transaction centrally on the server
                action_id = await action_engine.register_pending_action(
                    user_id=user_id,
                    action_type=act_type,
                    payload=payload,
                    trace_id=trace_id
                )

                # Replace with standardized Universal Action Card manifest payload
                processed_action = {
                    "type": "action_card",
                    "card_type": f"{act_type}_card",
                    "action_id": action_id,
                    "payload": {
                        "symbol": payload.get("symbol"),
                        "description": f"Goedkeuring vereist voor actie: {act_type}."
                    }
                }

        return processed_action, processed_draft


    async def get_assistant_insight(self, user_id: int, context_data: Dict[str, str]) -> Dict[str, Any]:
        start_insight = time.perf_counter()
        symbol = context_data.get("symbol", "BTC")
        page_type = context_data.get("page_type") or context_data.get("page") or "Dashboard"
        trader_profile_context: Dict[str, Any] = {}
        user = None

        if self.context_repo:
            finn_session = self.context_repo.session
        else:
            finn_session = getattr(self.score_repo, "db", None)

        try:
            if self.context_repo:
                user = await self.context_repo.user_repo.get_by_id(user_id)
            else:
                user = await self.user_repo.get_by_id(user_id)
        except Exception:
            user = None

        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        user_name = getattr(user, "first_name", "Trader") if user else "Trader"
        trader_profile_context = build_trader_profile_context(
            preferences,
            request_context=context_data,
            query=f"Wat moet ik vandaag doen met mijn {symbol} setup?",
        )

        if finn_session:
            try:
                finn = FinnPlanService(finn_session)
                daily_context = {"symbol": symbol, "page": page_type, **trader_profile_context}
                daily = await finn.build_daily_coach_response(
                    user_id,
                    f"Wat moet ik vandaag doen met mijn {symbol} setup?",
                    daily_context,
                )
                analysis = (daily.get("state") or {}).get("analysis") or {}
                briefing = self._assistant_insight_from_daily_coach(
                    symbol=symbol,
                    page_type=str(page_type),
                    daily_response=daily,
                    analysis=analysis,
                    context=daily_context,
                )
                if briefing:
                    insight_total_duration = (time.perf_counter() - start_insight) * 1000
                    logger.info("⏱️ [Ai-Assistant-Service] deterministic FINN insight took %.2fms", insight_total_duration)
                    return briefing
            except Exception as exc:
                logger.warning("⚠️ Deterministic FINN insight fallback failed: %s", exc, exc_info=True)
        
        # 1. Fetch Contexts, Market Data, and User Preferences sequentially to prevent task collisions
        if self.context_repo:
            market_context = await self.context_repo.build_context_sequential(user_id, "analysis")
            bot_context = await self.context_repo.build_context_sequential(user_id, "coach")
            live_data = await self.context_repo.market_data_repo.get_latest_market_data(symbol)
            user = await self.context_repo.user_repo.get_by_id(user_id)
        else:
            market_context = await self._build_context(user_id, "analysis")
            bot_context = await self._build_context(user_id, "coach")
            live_data = await self.market_data_repo.get_latest_market_data(symbol)
            user = await self.user_repo.get_by_id(user_id)
        
        db_duration_ms = (time.perf_counter() - start_insight) * 1000
        logger.info(f"⚡ [Ai-Assistant-Service] INSIGHT DATABASE GATHER SEQUENTIAL took {db_duration_ms:.2f}ms")

        live_context = "No live data available."
        if live_data:
            live_context = (
                f"CURRENT PRICE: ${live_data.price:,.2f}\n"
                f"24H CHANGE: {live_data.change_24h}%\n"
                f"TIMESTAMP: {live_data.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"
            )
        
        # 2. Get User Preferences & Name
        adaptive_profile_str = _build_adaptive_profile_str(preferences, None, user_name)

        # 3. Build System Prompt (Combined role for speed/brevity)
        raw_system_role = get_role_prompt("combined_insight", preferences)
        timeframe = context_data.get("timeframe", "Snapshot")
        
        # Manually replace placeholders in the system role task description
        system_role = (
            raw_system_role.replace("{user_name}", user_name)
            .replace("{page}", page_type)
            .replace("{symbol}", symbol)
            + f"\n\nTRADER PROFILE CONTEXT:\n{adaptive_profile_str}\n"
        )

        # 4. Generate Insight via GATEWAY (Single Call)
        prompt = (
            f"GENERATE ACTION-ORIENTED TRADING INSIGHT\n\n"
            f"--- LIVE MARKET DATA ({symbol}) ---\n"
            f"{live_context}\n\n"
            f"--- MARKET ANALYSIS CONTEXT ---\n"
            f"{market_context}\n\n"
            f"--- BOT & PERFORMANCE CONTEXT ---\n"
            f"{bot_context}\n\n"
            f"--- CONTEXT DATA ---\n"
            f"USER: {user_name} | PAGE: {page_type} | ASSET: {symbol} | TIME: {timeframe}\n\n"
            f"--- INSTRUCTIONS ---\n"
            f"- GREETING: Exactly 1 sentence (Hoi {user_name}, {symbol} price and trend summary...).\n"
            f"- CONCLUSION/ACTION: Exactly 1 sentence each. Make sure they use the real-time price and technical metrics from the contexts above. Never hallucinate outdated values (like $30,000 for BTC) unless it matches the live data.\n"
            f"- WHY: Technical reasoning (RSI/price/metrics) in max 2 sentences based strictly on the provided contexts.\n"
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
            timeframe=timeframe,
            user_model=user
        )

        insight_total_duration = (time.perf_counter() - start_insight) * 1000
        logger.info(f"⏱️ [Ai-Assistant-Service] TOTAL get_assistant_insight execution took {insight_total_duration:.2f}ms")

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
                },
                "suggested_actions": ["DCA setup maken", "Mijn bots bekijken", "Risico aanpassen"]
            }
        
        # Enforce valid suggested_actions list in parsed result
        if "suggested_actions" not in insight or not isinstance(insight["suggested_actions"], list):
            insight["suggested_actions"] = ["Pas bot aan", "DCA setup maken", "Risico aanpassen"]
        
        return insight

    def _assistant_insight_from_daily_coach(
        self,
        *,
        symbol: str,
        page_type: str,
        daily_response: Dict[str, Any],
        analysis: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not analysis:
            return None

        stance = analysis.get("stance")
        setup = analysis.get("setup") or {}
        blockers = analysis.get("blockers") or []
        bot_today = analysis.get("bot_today") or {}
        indicator_summary = analysis.get("indicator_summary") or {}
        warnings = indicator_summary.get("warnings") or []
        suggestions = analysis.get("suggested_actions") or []

        if stance == "plan_is_active":
            posture = "Plan Active"
            conclusion = f"{symbol} voldoet vandaag aan je setup-ranges."
            action = "Volg je plan en review een bot-proposal voordat je uitvoert."
        elif stance == "wait_for_scores":
            posture = "Data Pending"
            conclusion = f"{symbol} heeft nog geen volledige daily score voor een betrouwbaar oordeel."
            action = "Wacht op scoredata voordat je een trade- of DCA-beslissing neemt."
        else:
            posture = "Defensive Posture"
            conclusion = f"{symbol} is vandaag geblokkeerd volgens je eigen planregels."
            action = "Niet forceren; wacht tot de blocker-scores binnen je ranges vallen."

        profile_used = bool((context or {}).get("trader_profile_used"))
        trader_types = set(((context or {}).get("trader_profile") or {}).get("trader_types") or [])
        experience_levels = set(((context or {}).get("trader_profile") or {}).get("experience_levels") or [])
        risk_profiles = set(((context or {}).get("trader_profile") or {}).get("risk_profiles") or [])
        behavior_flags = set(((context or {}).get("trader_profile") or {}).get("behavior_flags") or [])
        if profile_used:
            if trader_types & {"investor", "dca_investor"}:
                action = f"Voor jouw langere horizon hoef je {symbol} nu niet te forceren; toets eerst of dit je plan echt verandert."
            elif "swing_trader" in trader_types:
                action = f"Voor jouw swing-profiel telt nu vooral of {symbol} op 4H/Daily bevestiging terugpakt."
            elif trader_types & {"day_trader", "scalper"}:
                action = f"Voor jouw kortere horizon wil je voor {symbol} eerst timing- en momentumbevestiging zien."
            if "beginner" in experience_levels:
                why_prefix = "Kort gezegd: "
            else:
                why_prefix = ""
            if "conservative" in risk_profiles and stance != "plan_is_active":
                conclusion = f"{symbol} vraagt nu extra geduld voor jouw risicoprofiel."
                if trader_types & {"investor", "dca_investor"}:
                    action = f"Voor jouw langere horizon hoef je {symbol} nu niet te forceren; wacht tot de sterkste blocker echt weg is."
                elif "swing_trader" in trader_types:
                    action = f"Voor jouw swing-profiel wacht je met nieuwe actie in {symbol} tot bevestiging en blockers beter liggen."
                elif trader_types & {"day_trader", "scalper"}:
                    action = f"Voor jouw kortere horizon stap je nu niet in {symbol} tot timing en blockers weer meewerken."
                else:
                    action = f"Wacht met nieuwe actie in {symbol} tot de sterkste blocker echt weg is."
            if "fomo" in behavior_flags:
                action = f"Wacht bij {symbol} eerst op bevestiging; laat geen haast of FOMO je timing overnemen."
                conclusion = f"{conclusion} Je coachingsprofiel vraagt hier extra rust."
            elif "overtrades" in behavior_flags:
                action = f"Voeg voor {symbol} nu alleen iets toe als deze stap duidelijk beter is dan je laatste actie."
            elif "holds_losers_too_long" in behavior_flags:
                action = f"Check voor {symbol} eerst je invalidatie en exitgrens voordat je iets laat doorlopen."
            elif "takes_profit_too_early" in behavior_flags:
                action = f"Leg voor {symbol} eerst je exitplan vast zodat je een winnaar niet te vroeg dichtzet."
            elif "leverage_seeking" in behavior_flags:
                action = f"Gebruik voor {symbol} eerst de minst agressieve uitvoering; leverage is hier geen shortcut."
        else:
            why_prefix = ""

        if blockers:
            blocker_text = "; ".join(
                f"{b.get('category')} {b.get('score')} buiten {b.get('range')}"
                for b in blockers[:3]
            )
            why = f"{why_prefix}Blockers: {blocker_text}."
        elif not analysis.get("has_scores"):
            why = f"{why_prefix}Er is onvoldoende scoredata; Finn geeft daarom geen fake actief/inactief conclusie."
        else:
            why = f"{why_prefix}Macro, technical en market passen bij je setup-ranges."

        if setup:
            why += f" Setup: {setup.get('name')} (#{setup.get('id')}), match {analysis.get('setup_match_percentage')}%."
        if profile_used:
            if "fomo" in behavior_flags:
                why += " FOMO maakt timing fragieler als bevestiging nog ontbreekt."
            elif "overtrades" in behavior_flags:
                why += " Extra activiteit voelt snel als controle, maar kan hier vooral ruis toevoegen."

        bot_count = int(bot_today.get("decision_count") or 0)
        bot_conclusion = f"{bot_count} bot-beslissing(en) voor vandaag."
        bot_action = "Review open bot-beslissingen handmatig." if bot_count else "Geen bot-actie nodig zolang er geen decision klaarstaat."
        bot_why = "Finn voert niets automatisch uit vanuit de briefing."

        market_why_parts = [why]
        if warnings:
            market_why_parts.append("Data aandacht: " + "; ".join(str(w) for w in warnings[:2]) + ".")

        return {
            "greeting": f"Hoi, {symbol} briefing voor {page_type}: {posture}.",
            "bot_insight": {
                "conclusion": bot_conclusion,
                "action": bot_action,
                "why": bot_why,
            },
            "market_insight": {
                "conclusion": conclusion,
                "action": action,
                "why": " ".join(market_why_parts),
            },
            "context_detected": {
                "symbol": symbol,
                "page": page_type,
                "flow": "daily_coach",
                "stance": stance,
                "posture": posture,
            },
            "suggested_actions": suggestions[:4] or ["Vraag Finn om mijn plan uit te leggen", "Bekijk setup blockers"],
            "daily_coach": analysis,
            "briefing_text": daily_response.get("response"),
        }

    def _build_flow_registry_prompt(self, conv_state: Optional[dict], stated_exp: str) -> str:
        from backend.ai_agents.flow_registry import FLOW_DEFINITIONS
        import json

        locale = _resolve_locale(getattr(self, "_active_preferences", None))
        response_language = _response_language_name(getattr(self, "_active_preferences", None))
        active_flow_name = conv_state.get("current_flow") if conv_state else None
        if active_flow_name and active_flow_name in FLOW_DEFINITIONS:
            flow = FLOW_DEFINITIONS[active_flow_name]
            # Build specific instructions for the active flow
            question_guide = []
            for q in flow.get("question_sequence", []):
                q_text = q.get(f"question_{stated_exp}", q.get("question_beginner"))
                question_guide.append(f"- For slot '{q['slot']}': Use question: \"{q_text}\"")
            
            question_guide_str = "\n".join(question_guide)
            conditional_str = json.dumps(flow.get("conditional_slots", {}))

            symbol = conv_state.get("slots", {}).get("symbol", "BTC")
            redirect_msg = ""
            if conv_state.get("redirect_reason") == "no_setup":
                redirect_msg = (
                    f"\n[ALERT: REDIRECTED FLOW] The user requested a Strategy for '{symbol}', but there is NO Setup (Blueprint) for this asset yet. "
                    f"You have been redirected to start a 'setup_creation' flow for '{symbol}' first. "
                    f"Briefly explain this in {response_language} "
                    f"(concise, e.g. '{_localized_example_text(getattr(self, '_active_preferences', None), 'no_setup', symbol)}') "
                    f"and then ask the first question of setup_creation: '{_localized_example_text(getattr(self, '_active_preferences', None), 'setup_type_question', symbol)}'"
                )
            elif conv_state.get("redirect_reason") == "no_strategy":
                redirect_msg = (
                    f"\n[ALERT: REDIRECTED FLOW] The user requested a Bot for '{symbol}', but there is NO Strategy for this asset yet. "
                    f"You have been redirected to start a 'strategy_creation' flow for '{symbol}' first. "
                    f"Briefly explain this in {response_language} "
                    f"(concise, e.g. '{_localized_example_text(getattr(self, '_active_preferences', None), 'no_strategy', symbol)}') "
                    f"and then ask the first question of strategy_creation in {response_language}."
                )
            elif conv_state.get("redirect_reason") == "no_setup_nor_strategy":
                redirect_msg = (
                    f"\n[ALERT: REDIRECTED FLOW] The user requested a Bot for '{symbol}', but there is NO Setup or Strategy for this asset yet. "
                    f"You have been redirected to start a 'setup_creation' flow for '{symbol}' first. "
                    f"Briefly explain this in {response_language} "
                    f"(concise, e.g. '{_localized_example_text(getattr(self, '_active_preferences', None), 'no_setup_nor_strategy', symbol)}') "
                    f"and then ask the first question of setup_creation: '{_localized_example_text(getattr(self, '_active_preferences', None), 'setup_type_question', symbol)}'"
                )

            return (
                f"\n=== ACTIVE CONVERSATIONAL FLOW MANDATE (FLOW REGISTRY) ===\n"
                f"You are currently executing the active flow: '{active_flow_name}'\n"
                f"Your active Role is: '{flow.get('assistant_role')}'\n"
                f"Target Page for this flow: {flow.get('page')}\n"
                f"Primary required slots: {json.dumps(flow.get('required_slots'))}\n"
                f"Conditional slots: {conditional_str}\n"
                f"Already collected slots: {json.dumps(conv_state.get('slots', {}))}\n"
                f"{redirect_msg}\n\n"
                f"=== SLOT SCHEMA DEFINITIONS REFERENCE ===\n"
                f"Extract user answers into 'state.slots' using these rules:\n"
                f"- 'symbol': uppercase string ticker (e.g., 'SOL', 'BTC', 'ETH').\n"
                f"- 'setup_type': must be exactly 'dca' or 'trade'. Extract 'dca' if user says 'dca' or 'passief bijkopen'; extract 'trade' if user says 'trade', 'actieve handmatige', or 'actief'.\n"
                f"- 'dca_frequency': must be exactly 'daily', 'weekly', or 'monthly'.\n"
                f"- 'base_amount': numeric value (e.g., 100).\n"
                f"- 'entry': numeric value (e.g., 150.0).\n"
                f"- 'targets': array of numeric values (e.g., [160.0, 170.0, 180.0]).\n"
                f"- 'stop_loss': numeric value (e.g., 140.0).\n"
                f"- 'name': string name (e.g., 'SOL Autopilot Bot').\n"
                f"- 'budget_total_eur': numeric value (e.g., 500).\n\n"
                f"=== STRICT ACTIVE FLOW CONCISENESS MANDATE ===\n"
                f"1. OPERATOR TONE (STRICT): Act as a premium, quiet, direct trading assistant. Write at most ONE short, clear, direct sentence per turn. Speak in {response_language}.\n"
                f"2. OPERATOR VOICE EXAMPLES:\n"
                f"   - Use formats like 'SOL setup voorbereid.' ONLY when ALL required slots are collected and the draft is ready.\n"
                f"   - NEVER say: 'Perfect! Ik heb de setup voor BTC klaargezet...' or 'Ik heb de parameters voor je ingesteld...'. Keep it extremely short and direct.\n"
                f"3. ZERO FILLER: Do NOT use polite conversational fillers or pleasantries (e.g., do NOT say 'Prima, we gaan...', 'Laten we de nieuwe...', 'Goed idee...').\n"
                f"4. NO REPETITION: Do NOT repeat back any context, existing setups, or fields the user already provided. Just state the next prompt.\n"
                f"5. ONLY 1 QUESTION: Ask EXACTLY ONE question to gather the next missing slot. Do NOT just say 'voorbeid' if there are still missing slots!\n"
                f"6. NO DISCLAIMERS: Under no circumstances output any disclaimer, safety note, or 'not financial advice' warning. Keep responses strictly concise and direct.\n"
                f"7. FALLBACKS: If the user is unsure or gives an invalid answer for a slot (e.g., '{'geen idee' if locale == 'nl' else 'not sure'}'), you MUST suggest a reasonable default and ask for confirmation in {response_language}.\n\n"
                f"CRITICAL INSTRUCTIONS:\n"
                f"1. You MUST continue this flow. Keep 'draft' as null until ALL required slots (and conditional slots if applicable) are collected.\n"
                f"2. SLOT EXTRACTION (MANDATORY): You must extract the value for the current missing slot from the user's latest query (USER QUERY) and add/update it in 'state.slots'.\n"
                f"3. Set state.current_flow to '{active_flow_name}' and state.status to 'collecting' and state.slots to the accumulated dictionary of slots.\n"
                f"   - IMPORTANT (FLOW SWITCHING / RESET): If the user's latest query explicitly requests a NEW setup, strategy, or bot for a DIFFERENT asset (e.g. asking to make a setup for ETH while the active slots are for SOL), you MUST clear the old slots and start a fresh sequence. Set state.slots to only have the new symbol (e.g., {{'symbol': 'ETH'}}), set state.current_flow to '{active_flow_name}', and ask the user for the next slot (the setup_type).\n"
                f"   - Do NOT mix up or keep slots from the previous asset (e.g. do not keep 'dca_frequency' or 'setup_type' from the old SOL setup if the user is asking to create a setup for ETH).\n"
                f"4. Identify the NEXT missing slot in the sequence for the current active flow. Ask the user ONLY for that next missing slot. Do NOT ask for slots that the user has already provided in their latest message (e.g. if the user says 'make setup for ETH', then 'symbol' is already 'ETH' and is NOT missing, so ask for 'setup_type' instead!).\n"
                f"   Use or closely adapt the corresponding question from this guide:\n"
                f"{question_guide_str}\n"
                f"5. Once ALL slots are gathered, set state.current_flow to 'none', state.status to 'complete', state.slots to {{}}, and populate the final 'draft' with type '{flow.get('draft_type')}' using payload matching the fields. Present the draft card to the user.\n"
                f"6. CONFIRMATION / FINALIZATION TRIGGER: If the user says 'maak de setup', 'maak nu', 'opslaan', or 'finaliseer', you MUST immediately mark the flow as 'complete' (set state.status to 'complete', state.current_flow to 'none'), populate the draft object with all slots gathered so far (using standard defaults for any missing ones), and present the draft card to the user. Do NOT ask for more slots if they explicitly command to finish/make the setup.\n"
            )
        else:
            # List candidate flows so LLM can trigger them
            flows_list = []
            for name, defs in FLOW_DEFINITIONS.items():
                flows_list.append(
                    f"- '{name}': Role: '{defs.get('assistant_role')}', Slots: {json.dumps(defs.get('required_slots'))}, Draft Type: {defs.get('draft_type')}"
                )
            flows_str = "\n".join(flows_list)
            return (
                f"\n=== AVAILABLE CONVERSATIONAL FLOWS (FLOW REGISTRY) ===\n"
                f"If the user wants to start an interactive workflow or action, you must transition them into one of these flows by setting 'state.current_flow' to the flow name and state.status to 'collecting' and initiating the questions:\n"
                f"{flows_str}\n\n"
                f"FLOW START INSTRUCTIONS:\n"
                f"- When transitioning, extract any slots already present in the user query and put them in state.slots.\n"
                f"- Begin asking for the first missing slot using the flow's question sequence.\n"
            )

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
        if any(w in q for w in ["hoi", "wie ben", "hello", "hi", "heej", "yo", "annuleer", "laat maar", "reset"]):
            return "chat"
        if any(w in q for w in ["onboarding", "start intro", "kennismaken", "profiel instellen", "start onboarding"]):
            return "user_onboarding"
        if any(w in q for w in ["dca", "setup", "interval"]):
            return "dca_setup"
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
        started = time.perf_counter()
        try:
            cache_key = f"{int(user_id)}:{str(intent or 'general').strip().lower()}"
            cached = _get_cached_assistant_context(cache_key)
            if cached is not None:
                return cached
            context_parts = []
            today = date.today()

            if intent == "decision":
                # The repositories behind this service often share one AsyncSession.
                # Keep these reads sequential to avoid concurrent session use.
                scores = await self.score_repo.get_master_score(user_id)
                setups = await self.setup_repo.get_user_setups(user_id)
                context_parts.append(f"CURRENT MASTER SCORE: {scores.avg_score if scores else 'N/A'}")
                context_parts.append(f"ACTIVE SETUPS: {[s.name for s in setups]}")

            elif intent == "report":
                # Latest Report
                report = await self.report_repo.get_latest_report(user_id, "daily_reports")
                context_parts.append(f"LATEST DAILY REPORT: {report.get('summary') if report else 'No report available'}")

            elif intent == "coach":
                # Strategy and history are read sequentially to keep the shared
                # SQLAlchemy AsyncSession task-safe.
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
                # 📊 Market Trends & Scores with Global Fallback parallelized
                categories = ["macro", "market", "technical"]
                category_data = {}

                async def get_insight_for_category(cat):
                    stmt = select(AiCategoryInsight).where(
                        AiCategoryInsight.user_id == user_id,
                        AiCategoryInsight.category == cat
                    ).order_by(AiCategoryInsight.date.desc()).limit(1)
                    
                    res = await self.score_repo.db.execute(stmt)
                    user_insight = res.scalars().first()

                    if user_insight:
                        return cat, {
                            "summary": user_insight.summary,
                            "bias": user_insight.bias,
                            "score": float(user_insight.avg_score or 0)
                        }
                    else:
                        global_insight = await self.score_repo.get_global_insight(cat)
                        if global_insight:
                            return cat, {
                                "summary": global_insight["summary"],
                                "bias": global_insight["bias"],
                                "score": float(global_insight["avg_score"] or 0),
                                "note": "GLOBAL_FALLBACK"
                            }
                        return cat, None

                for cat in categories:
                    _, data = await get_insight_for_category(cat)
                    if data:
                        category_data[cat] = data

                context_parts.append(f"AI ANALYSIS CONTEXT: {category_data}")

            # Always add basic context if needed or fallbacks
            if not context_parts:
                context_parts.append("General assistance mode. No specific deep context loaded.")

            context_value = "\n".join(context_parts)
            _store_cached_assistant_context(cache_key, context_value)
            return context_value
        finally:
            record_latency_sample(
                "assistant_context_latency_ms",
                (time.perf_counter() - started) * 1000,
            )

    async def _handle_implicit_feedback(self, user_id: int, query: str):
        # Selective preference updates only for style/tone/adaptive feedback
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
            
        # EXPLICIT COMMANDS (Immediate DB Updates)
        # Check if user explicitly commands a preference mutation (e.g. "zet ", "verander ", "pas aan", "update ")
        is_explicit = any(cmd in q for cmd in ["zet ", "verander ", "pas ", "update ", "wijzig ", "schakel ", "instellen "])
        
        if is_explicit:
            # 1. Experience Level
            if "gevorderd" in q or "advanced" in q or "expert" in q or "ervaren" in q:
                updates["experience_level"] = "advanced"
            elif "beginner" in q or "nieuw" in q or "starter" in q or "amateur" in q:
                updates["experience_level"] = "beginner"
                
            # 2. Risk Profile
            if "conservatief" in q or "voorzichtig" in q or "laag risico" in q or "veilig" in q:
                updates["risk_profile"] = "conservative"
            elif "agressief" in q or "hoog risico" in q or "vol gas" in q or "risicovol" in q:
                updates["risk_profile"] = "aggressive"
            elif "gebalanceerd" in q or "neutraal" in q or "balanced" in q or "medium risico" in q:
                updates["risk_profile"] = "balanced"
        
        if updates:
            await self.user_repo.update_ai_preferences(user_id, updates)
            logger.info(f"Updated AI preferences for user {user_id}: {updates}")

    def _build_portfolio_context_str(self, pi: Dict[str, Any]) -> str:
        g = pi.get("global", {})
        allocs = ", ".join(f"{k}: {v}%" for k, v in g.get("allocations_pct", {}).items())
        
        lines = [
            "REAL-TIME PORTFOLIO & ASSET BALANCES:",
            f"- Total Equity: EUR {g.get('total_equity', 0.0):,.2f}",
            f"- Cash Balance (Unused): EUR {g.get('cash_balance', 0.0):,.2f}",
            f"- Invested Value (Cost Basis): EUR {g.get('invested_value', 0.0):,.2f}",
            f"- Current Positions Value: EUR {g.get('current_position_value', 0.0):,.2f}",
            f"- Realized PnL: EUR {g.get('realized_pnl', 0.0):,.2f}",
            f"- Unrealized PnL: EUR {g.get('unrealized_pnl', 0.0):,.2f}",
            f"- Global Budget Limit (Sum of all Bot Budgets): EUR {g.get('total_budget_limit', 0.0):,.2f}",
            f"- Asset Allocations: {allocs}",
            "",
            "ACTIVE BOT PORTFOLIOS:"
        ]
        
        bots = pi.get("bots", [])
        if not bots:
            lines.append("  No active trading bots configured.")
        for b in bots:
            lines.append(
                f"  * Bot '{b['name']}' (ID: {b['bot_id']}, Asset: {b['symbol']}):\n"
                f"    - Status: {'Active' if b['is_active'] else 'Inactive'} | Mode: {'Live' if b['is_live'] else 'Simulation'}\n"
                f"    - Cash Balance: EUR {b['cash']:,.2f}\n"
                f"    - Asset Quantity: {b['qty']}\n"
                f"    - Invested Cost Basis: EUR {b['invested']:,.2f}\n"
                f"    - Current Asset Value: EUR {b['position_value']:,.2f}\n"
                f"    - Avg Entry Price: EUR {b['avg_entry']:,.2f}\n"
                f"    - Realized PnL: EUR {b['realized_pnl']:,.2f}\n"
                f"    - Unrealized PnL: EUR {b['unrealized_pnl']:,.2f}\n"
                f"    - Assigned Budget: EUR {b['budget_total']:,.2f} | Risk Profile: {b['risk_profile']}"
            )
            
        lines.extend([
            "",
            "PORTFOLIO COACHING INSTRUCTIONS & GUARDRAILS:",
            "1. REACTION TO QUESTIONS: Use these real-time, exact numbers when answering questions about total equity, cash, specific coin holdings, average entries, or bot metrics. Be extremely precise. Never make up or hallucinate figures.",
            "2. RISK ANALYSIS (PROACTIVE COACHING):",
            "   - OVERALLOCATION: If a single volatile asset (like SOL or BTC) represents >60% of total equity, gently warn Henk about high concentration risk and suggest diversification.",
            "   - LOW CASH: If cash balance represents <10% of total equity, advise caution regarding liquidity and suggest keeping a reserve for market drawdowns.",
            "3. BUDGET PRE-CHECKS: If Henk discusses creating a setup/bot or modifying a budget:",
            "   - Compare the proposed budget with his global Cash Balance (Unused).",
            "   - If the proposed budget exceeds his Cash Balance, advise him that he has insufficient unused cash and should either reduce the budget or deposit more funds.",
            "4. STRIKT READ-ONLY GUARDRAILS:",
            "   - You are a READ-ONLY advisory layer. You MUST NOT execute, schedule, or propose automatic buy/sell transactions.",
            "   - Never give hard investment recommendations or explicit 'buy' or 'sell' calls. Instead, provide educational scenarios, balance analyses, and strategic parameters based on his risk profile.",
            "   - ABSOLUTE PROHIBITION of guessing, estimation, or extrapolation. If data is missing or incomplete for any metric, do NOT guess. State clearly that the data is not available."
        ])
        
        return "\n".join(lines)

    async def _build_continuity_context_str(self, user_id: int) -> str:
        """
        Synthesiseert een chronologisch overzicht van recente acties, gedetecteerde risico's,
        en eerdere chatsessies om FINN continuïteit en persistent geheugen te geven.
        """
        try:
            # 1. Haal recente goedgekeurde acties op
            stmt_actions = (
                select(AiPendingAction)
                .where(and_(AiPendingAction.user_id == user_id, AiPendingAction.status == 'executed'))
                .order_by(desc(AiPendingAction.created_at))
                .limit(3)
            )
            res_actions = await self.state_repo.session.execute(stmt_actions)
            executed_actions = res_actions.scalars().all()

            # 2. Haal actieve intelligence events op
            stmt_events = (
                select(AiIntelligenceEvent)
                .where(and_(AiIntelligenceEvent.user_id == user_id, AiIntelligenceEvent.status == 'active'))
                .order_by(desc(AiIntelligenceEvent.created_at))
                .limit(5)
            )
            res_events = await self.state_repo.session.execute(stmt_events)
            active_events = res_events.scalars().all()

            lines = ["CHRONOLOGISCHE CONTINUÏTEIT EN GEHEUGEN (SINGLE SOURCE OF TRUTH):"]
            
            if executed_actions:
                lines.append("- RECENT DOOR GEBRUIKER GEACTIVEERDE ACTIES (Approved via Card):")
                for act in executed_actions:
                    dt_str = act.created_at.strftime('%Y-%m-%d %H:%M') if act.created_at else "onbekend"
                    lines.append(f"  * [{dt_str}] Type '{act.type}' is succesvol uitgevoerd door de handelaar.")
            else:
                lines.append("- Geen recent goedgekeurde acties in database.")

            if active_events:
                lines.append("- RECENT LIVE ASSISTANT INTELLIGENCE EVENTS:")
                for ev in active_events:
                    dt_str = ev.created_at.strftime('%Y-%m-%d %H:%M') if ev.created_at else "onbekend"
                    lines.append(f"  * [{dt_str}] [{ev.severity.upper()}] {ev.title}: {ev.description}")
            else:
                lines.append("- Geen actieve risico- of marktevenementen gedetecteerd.")

            return "\n".join(lines)
        except Exception as e:
            logger.error(f"Error in _build_continuity_context_str: {e}")
            return "CHRONOLOGISCHE CONTINUÏTEIT: Tijdelijk niet beschikbaar door een interne service fout."


async def _get_supported_ai_usage_log_columns(db_session) -> set[str]:
    global _ai_usage_log_supported_columns
    if _ai_usage_log_supported_columns:
        return _ai_usage_log_supported_columns

    try:
        result = await db_session.execute(text("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'ai_usage_logs'
        """))
        rows = result.fetchall()
        columns = {str(row[0]) for row in rows if row and row[0]}
        if columns:
            _ai_usage_log_supported_columns = columns
            return columns
    except Exception as exc:
        logger.warning("⚠️ Kon ai_usage_logs schema niet inspecteren in background logger; gebruik volledige kolomset: %s", exc)

    _ai_usage_log_supported_columns = set(AI_USAGE_LOG_COLUMN_ORDER)
    return _ai_usage_log_supported_columns


async def record_ai_usage_background(
    user_id: int,
    user_query: str,
    prompt: str,
    chat_text: str,
    intent: str,
    resolved_symbol: str,
    trace_id: str,
    duration_ms: int,
    confidence_score: Optional[float] = None,
    parser_recovery_triggered: bool = False,
    safety_guardrail_triggered: bool = False,
    completion_status: str = "success"
):
    """
    🛡️ Async non-blocking background worker task for DB updates.
    Runs in isolated session context to prevent any thread or connection pooling conflicts.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    from backend.infrastructure.database import async_session_factory
    async with async_session_factory() as db:
        try:
            from backend.infrastructure.repositories.user_repository import UserRepository
            user_repo = UserRepository(db)
            
            p_tokens = int((len(user_query) + len(prompt)) / 4)
            c_tokens = int(len(chat_text) / 4)
            
            from backend.utils.ai_cost_calculator import calculate_cost
            cost = calculate_cost("gpt-4o-mini", p_tokens, c_tokens)
            
            from backend.services.ai_usage_observability_service import classify_request_source

            user = await user_repo.get_by_id(user_id)
            user_email = getattr(user, "email", None) if user else None
            app_env = os.getenv("APP_ENV", "unknown")
            request_source = classify_request_source(
                user_email=user_email,
                app_env=app_env,
                run_kind="interactive",
            )
            supported_columns = await _get_supported_ai_usage_log_columns(db)
            values = {
                "user_id": user_id,
                "model": "gpt-4o-mini",
                "prompt_tokens": p_tokens,
                "completion_tokens": c_tokens,
                "cost": cost,
                "purpose": f"chat_{intent}",
                "status": "full_ai",
                "response_time_ms": duration_ms,
                "estimated_cost_if_full": cost,
                "symbol": resolved_symbol,
                "trace_id": trace_id,
                "completion_status": completion_status,
                "parser_recovery_triggered": parser_recovery_triggered,
                "confidence_score": confidence_score,
                "safety_guardrail_triggered": safety_guardrail_triggered,
                "request_source": request_source,
                "app_env": app_env,
                "run_kind": "interactive",
                "entry_point": f"assistant_service:{intent}",
                "user_email_snapshot": user_email,
            }
            columns, params = filter_ai_usage_log_values(values, supported_columns=supported_columns)
            stmt = text(
                "INSERT INTO ai_usage_logs ("
                + ", ".join(columns)
                + ") VALUES ("
                + ", ".join(f":{column}" for column in columns)
                + ")"
            )
            await db.execute(stmt, params)
            
            # Increment request counter and cost statistics
            await user_repo.update_ai_usage(user_id, 1, cost, p_tokens + c_tokens)
            await db.commit()
            logger.info(f"📊 [Background-Logger] Successfully recorded usage metrics for trace {trace_id}")
        except Exception as ue:
            logger.error(f"❌ Background logger error for trace {trace_id}: {ue}")
            await db.rollback()
