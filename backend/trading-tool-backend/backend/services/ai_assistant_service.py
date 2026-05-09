import logging
import time
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, AsyncGenerator
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
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository

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

    async def get_chat_response(
        self, 
        user_id: int, 
        user_query: str, 
        history: Optional[List[Dict[str, Any]]] = None,
        context_data: Optional[Dict[str, str]] = None,
        trace_id: Optional[str] = None
    ) -> tuple[str, Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        # Start response time tracking
        self.start_overall_time = time.perf_counter()
        import uuid
        self.trace_id = trace_id or f"trdm-trace-{uuid.uuid4().hex[:8]}-{hex(int(time.time()))[2:]}"
        
        # 1. Classify Intent (Rule-based V1)
        intent = self._classify_intent(user_query)
        logger.info(f"🧠 Assistant Chat Intent: {intent} for query: {user_query}")
        
        # 1.1 Conversational Abort/Reset Engine Interceptor (Bypasses DB gather and LLM calls entirely!)
        abort_triggers = ["stop", "annuleer", "annuleren", "laat maar", "reset", "opnieuw beginnen", "wis alles", "wis setup"]
        q_lower = user_query.strip().lower()
        import re
        q_clean = re.sub(r'[^\w\s]', '', q_lower)
        
        if any(trigger in q_clean for trigger in abort_triggers):
            # Clear state in PostgreSQL immediately
            await self.state_repo.clear_state(user_id)
            logger.info(f"🧹 [Conversational-Abort-Engine] Cleared active conversation state for user {user_id} upon trigger: {user_query}")
            
            response_text = "Ik heb de huidige setup-flow voor je geannuleerd. Je kunt me altijd vragen om iets nieuws te starten of een andere vraag stellen! 👍"
            state_reset = {"current_flow": "none", "slots": {}, "status": "none"}
            return response_text, None, None, state_reset
        
        # 1.5 Active Asset Priority Engine & Sequential Context Gathering
        explicit_symbol = None
        symbols_to_check = ["BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "DOT", "AVAX", "LINK"]
        for sym in symbols_to_check:
            if re.search(r'\b' + sym + r'\b', user_query, re.IGNORECASE):
                explicit_symbol = sym.upper()
                break
                
        page_symbol = context_data.get("symbol") if context_data else None
        
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

        # Assemble Adaptive Intelligence Profile
        stated_exp = preferences.get("experience_level", "beginner")
        stated_risk = preferences.get("risk_profile", "balanced")
        
        adaptive_profile_str = (
            f"ADAPTIVE PERSONALIZATION PROFILE:\n"
            f"- Stated Experience Level (Preference): {stated_exp.upper()}\n"
            f"- Stated Risk Profile (Preference): {stated_risk.upper()}\n"
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
            f"3. CALIBRATING RISK THRESHOLDS & COACHING:\n"
            f"   - CONSERVATIVE PROFILE: Focus on downside protection and capital preservation. Proactively warn Henk if more than 40% of total equity is concentrated in a single volatile coin or if cash is low (<20%).\n"
            f"   - BALANCED PROFILE: Follow default risk limits (warn at >60% concentration or <10% cash) and recommend balanced asset-matching.\n"
            f"   - AGGRESSIVE PROFILE: Align with higher exposure allocations, but reinforce trading discipline. Warn only if asset concentration exceeds 80% and emphasize strict take-profit execution limits.\n"
            f"4. CASUAL PROFILE SIGNALS & CONFIDENCE PROPOSALS:\n"
            f"   - If Henk makes a casual statement indicating a level or risk that does NOT match his active Stated Preference (e.g. says 'vol gas' while on conservative, or says 'ik snap DCA niet' while on advanced):\n"
            f"     * Adapt your current response to his statement (e.g., be supportive or trade-focused for this turn).\n"
            f"     * DO NOT mutate his permanent profile behind his back. Instead, conversationally offer a polite proposal to update his settings: e.g. 'Ik merk dat je vaker agressievere setups bespreekt. Wil je dat ik je risicoprofiel aanpas naar agressief?'"
        )

        # 5. Build System Prompt
        system_role = get_role_prompt(role_key, preferences, intent=intent)

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
            f"ADAPTIVE INTELLIGENCE CONTEXT:\n{adaptive_profile_str}\n\n"
            f"FRONTEND METADATA:\n{context_data}"
        )

        # Build registry prompt instructions dynamically from central flow registry
        registry_instructions = self._build_flow_registry_prompt(conv_state, stated_exp)

        system_role_json = (
            system_role + 
            "\n\nIMPORTANT: You must return a JSON object with exactly five fields:\n"
            "- 'response': (string) your conversational response to the user's message in Dutch.\n"
            "- 'action': (object or null) if the user explicitly asks to add or remove a coin to/from their watchlist, "
            "or open pages, populate this object. Otherwise, set 'action' to null.\n"
            "- 'draft': (object or null) if the user asks to create/generate/setup a DCA setup, trading setup, strategy, or bot, "
            "populate this object. Otherwise, set 'draft' to null.\n"
            "- 'state': (object or null) current active conversation workflow state.\n"
            "- 'reasoning': (object or null) internal diagnostic reasoning containing: "
            "'confidence_score' (float, 0-100), 'risk_detected' (boolean), 'reasons' (list of strings), and "
            "'coaching_level' (string, e.g. 'beginner' or 'advanced').\n\n"
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

        if response_data:
            if isinstance(response_data, dict):
                chat_text = response_data.get("response", chat_text)
                action = response_data.get("action")
                draft = response_data.get("draft")
                state = response_data.get("state")
                reasoning = response_data.get("reasoning")
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

        # Apply deterministic safety post-processing guardrail to text response
        chat_text = self._apply_safety_guardrails(chat_text)

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

        # 7. Selective Preference Update (Optional/Explicit feedback)
        await self._handle_implicit_feedback(user_id, user_query)

        # Log total duration
        overall_duration_ms = (time.perf_counter() - self.start_overall_time) * 1000
        logger.info(
            f"⏱️ [Ai-Assistant-Service] TOTAL get_chat_response execution took {overall_duration_ms:.2f}ms "
            f"(DB sequential gather: {self.db_duration_ms:.2f}ms)"
        )

        return chat_text, action, draft, state, reasoning

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
        
        if any(trigger in q_clean for trigger in abort_triggers):
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
                
        page_symbol = context_data.get("symbol") if context_data else None
        
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
        logger.info(f"⚡ [Ai-Assistant-Service] SEQUENTIAL DATABASE CONTEXT GATHER (Stream) took {self.db_duration_ms:.2f}ms (Resolved Asset: {resolved_symbol})")

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

        # Assemble Adaptive Intelligence Profile
        stated_exp = preferences.get("experience_level", "beginner")
        stated_risk = preferences.get("risk_profile", "balanced")
        
        adaptive_profile_str = (
            f"ADAPTIVE PERSONALIZATION PROFILE:\n"
            f"- Stated Experience Level (Preference): {stated_exp.upper()}\n"
            f"- Stated Risk Profile (Preference): {stated_risk.upper()}\n"
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
            f"3. CALIBRATING RISK THRESHOLDS & COACHING:\n"
            f"   - CONSERVATIVE PROFILE: Focus on downside protection and capital preservation. Proactively warn Henk if more than 40% of total equity is concentrated in a single volatile coin or if cash is low (<20%).\n"
            f"   - BALANCED PROFILE: Follow default risk limits (warn at >60% concentration or <10% cash) and recommend balanced asset-matching.\n"
            f"   - AGGRESSIVE PROFILE: Align with higher exposure allocations, but reinforce trading discipline. Warn only if asset concentration exceeds 80% and emphasize strict take-profit execution limits.\n"
            f"4. CASUAL PROFILE SIGNALS & CONFIDENCE PROPOSALS:\n"
            f"   - If Henk makes a casual statement indicating a level or risk that does NOT match his active Stated Preference (e.g. says 'vol gas' while on conservative, or says 'ik snap DCA niet' while on advanced):\n"
            f"     * Adapt your current response to his statement (e.g., be supportive or trade-focused for this turn).\n"
            f"     * DO NOT mutate his permanent profile behind his back. Instead, conversationally offer a polite proposal to update his settings: e.g. 'Ik merk dat je vaker agressievere setups bespreekt. Wil je dat ik je risicoprofiel aanpas naar agressief?'"
        )

        # 5. Build System Prompt
        system_role = get_role_prompt(role_key, preferences, intent=intent)

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
            f"ADAPTIVE INTELLIGENCE CONTEXT:\n{adaptive_profile_str}\n\n"
            f"FRONTEND METADATA:\n{context_data}"
        )

        # Build registry prompt instructions dynamically from central flow registry
        registry_instructions = self._build_flow_registry_prompt(conv_state, stated_exp)

        system_role_json = (
            system_role + 
            "\n\nIMPORTANT: You must return a JSON object with exactly five fields:\n"
            "- 'response': (string) your conversational response to the user's message in Dutch.\n"
            "- 'action': (object or null) if the user explicitly asks to add or remove a coin to/from their watchlist, "
            "or open pages, populate this object. Otherwise, set 'action' to null.\n"
            "- 'draft': (object or null) if the user asks to create/generate/setup a DCA setup, trading setup, strategy, or bot, "
            "populate this object. Otherwise, set 'draft' to null.\n"
            "- 'state': (object or null) current active conversation workflow state.\n"
            "- 'reasoning': (object or null) internal diagnostic reasoning containing: "
            "'confidence_score' (float, 0-100), 'risk_detected' (boolean), 'reasons' (list of strings), and "
            "'coaching_level' (string, e.g. 'beginner' or 'advanced').\n\n"
            f"{registry_instructions}\n"
            "=== ACTION SCHEMAS ===\n"
            "The 'action' object can represent a SINGLE action or a BUNDLE of multiple actions:\n"
            "1. For SINGLE actions, 'type' must be one of ['add_to_watchlist', 'remove_from_watchlist', 'open_setup_page', 'generate_strategy', 'open_bot_draft', 'navigate_to_page'], and 'symbol' and 'params' should be populated.\n"
            "2. For 'navigate_to_page', you must specify 'params' with a 'path' key. ALLOWED_PATHS (strict whitelist): ['/dashboard', '/macro', '/technical', '/bot', '/strategy', '/setup', '/report', '/profile']. Any path outside this whitelist is strictly rejected.\n"
            "3. For MULTIPLE actions, 'type' must be 'bundle'. Then, populate the 'actions' array.\n\n"
            "=== SUGGESTED NEXT ACTIONS ===\n"
            "Always end your conversational response with 2-3 brief suggested action options under the Dutch header 'Volgende stappen:' as a bullet list, e.g.:\n"
            "- Bekijk macro analyse voor SOL\n"
            "- Start DCA bot setup\n"
            "- Open bot configuratie\n"
            "Make them highly relevant, concise, and clickable for the user!\n\n"
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

        if envelope:
            chat_text = envelope.get("response", chat_text)
            action = envelope.get("action")
            draft = envelope.get("draft")
            state = envelope.get("state")
            reasoning = envelope.get("reasoning")

        # Ensure types are strict and validate actions
        action = self._validate_and_sanitize_action(action)
        if not isinstance(draft, dict): draft = None
        if not isinstance(state, dict): state = None
        if not isinstance(reasoning, dict): reasoning = None

        # Apply safety guardrails to streamed text
        chat_text = self._apply_safety_guardrails(chat_text)

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
                "reasoning": reasoning
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
        trading_advices = ["kopen", "verkopen", "buy", "sell", "portfolio", "transactie", "allocation", "rendement"]
        if any(word in softened_text.lower() for word in trading_advices) and "Geen financieel advies" not in softened_text:
            softened_text += "\n\n*Disclaimer: Dit is uitsluitend educatieve en analytische informatie, geen direct koop- of verkoopadvies.*"
            
        return softened_text

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


    async def get_assistant_insight(self, user_id: int, context_data: Dict[str, str]) -> Dict[str, Any]:
        start_insight = time.perf_counter()
        symbol = context_data.get("symbol", "BTC")
        
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
        preferences = getattr(user, "ai_preferences", {}) or {} if user else {}
        user_name = getattr(user, "first_name", "Trader") if user else "Trader"

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
                }
            }
        
        return insight

    def _build_flow_registry_prompt(self, conv_state: Optional[dict], stated_exp: str) -> str:
        from backend.ai_agents.flow_registry import FLOW_DEFINITIONS
        import json

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

            return (
                f"\n=== ACTIVE CONVERSATIONAL FLOW MANDATE (FLOW REGISTRY) ===\n"
                f"You are currently executing the active flow: '{active_flow_name}'\n"
                f"Your active Role is: '{flow.get('assistant_role')}'\n"
                f"Target Page for this flow: {flow.get('page')}\n"
                f"Primary required slots: {json.dumps(flow.get('required_slots'))}\n"
                f"Conditional slots: {conditional_str}\n"
                f"Already collected slots: {json.dumps(conv_state.get('slots', {}))}\n\n"
                f"CRITICAL INSTRUCTIONS:\n"
                f"1. You MUST continue this flow. Keep 'draft' as null until ALL required slots (and conditional slots if applicable) are collected.\n"
                f"2. Set state.current_flow to '{active_flow_name}' and state.status to 'collecting' and state.slots to the accumulated dictionary of slots.\n"
                f"   - IMPORTANT (FLOW SWITCHING / RESET): If the user's latest query explicitly requests a NEW setup, strategy, or bot for a DIFFERENT asset (e.g. asking to make a setup for ETH while the active slots are for SOL), you MUST clear the old slots and start a fresh sequence. Set state.slots to only have the new symbol (e.g., {{'symbol': 'ETH'}}), set state.current_flow to '{active_flow_name}', and ask the user for the next slot (the setup_type).\n"
                f"   - Do NOT mix up or keep slots from the previous asset (e.g. do not keep 'dca_frequency' or 'setup_type' from the old SOL setup if the user is asking to create a setup for ETH).\n"
                f"3. Identify the NEXT missing slot in the sequence for the current active flow. Ask the user ONLY for that next missing slot. Do NOT ask for slots that the user has already provided in their latest message (e.g. if the user says 'make setup for ETH', then 'symbol' is already 'ETH' and is NOT missing, so ask for 'setup_type' instead!).\n"
                f"   Use or closely adapt the corresponding question from this guide:\n"
                f"{question_guide_str}\n"
                f"4. Once ALL slots are gathered, set state.current_flow to 'none', state.status to 'complete', state.slots to {{}}, and populate the final 'draft' with type '{flow.get('draft_type')}' using payload matching the fields. Present the draft card to the user.\n"
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
        context_parts = []
        today = date.today()

        if intent == "decision":
            # Scores & Setups parallelized
            scores, setups = await asyncio.gather(
                self.score_repo.get_master_score(user_id),
                self.setup_repo.get_user_setups(user_id)
            )
            context_parts.append(f"CURRENT MASTER SCORE: {scores.avg_score if scores else 'N/A'}")
            context_parts.append(f"ACTIVE SETUPS: {[s.name for s in setups]}")

        elif intent == "report":
            # Latest Report
            report = await self.report_repo.get_latest_report(user_id, "daily_reports")
            context_parts.append(f"LATEST DAILY REPORT: {report.get('summary') if report else 'No report available'}")

        elif intent == "coach":
            # 1. Fetch Strategy and History in parallel
            start_date = today - timedelta(days=7)
            strategy, history = await asyncio.gather(
                self.strategy_repo.get_last_strategy(user_id),
                self.bot_repo.get_bot_history(user_id, start_date, today)
            )

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

            results = await asyncio.gather(*(get_insight_for_category(cat) for cat in categories))
            for cat, data in results:
                if data:
                    category_data[cat] = data

            context_parts.append(f"AI ANALYSIS CONTEXT: {category_data}")

        # Always add basic context if needed or fallbacks
        if not context_parts:
            context_parts.append("General assistance mode. No specific deep context loaded.")

        return "\n".join(context_parts)

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
            
            from sqlalchemy import text
            stmt = text("""
                INSERT INTO ai_usage_logs (
                    user_id, model, prompt_tokens, completion_tokens, cost, purpose, status, 
                    response_time_ms, estimated_cost_if_full, symbol, trace_id, 
                    completion_status, parser_recovery_triggered, confidence_score, safety_guardrail_triggered
                ) VALUES (
                    :u, :m, :p, :c, :co, :pur, :s, 
                    :rt, :ec, :sym, :tid, 
                    :c_stat, :p_rec, :conf, :s_grd
                )
            """)
            await db.execute(stmt, {
                "u": user_id, "m": "gpt-4o-mini", "p": p_tokens, "c": c_tokens, "co": cost, "pur": f"chat_{intent}", "s": "full_ai",
                "rt": duration_ms, "ec": cost, "sym": resolved_symbol, "tid": trace_id,
                "c_stat": completion_status, "p_rec": parser_recovery_triggered, "conf": confidence_score, "s_grd": safety_guardrail_triggered
            })
            
            # Increment request counter and cost statistics
            await user_repo.update_ai_usage(user_id, 1, cost, p_tokens + c_tokens)
            await db.commit()
            logger.info(f"📊 [Background-Logger] Successfully recorded usage metrics for trace {trace_id}")
        except Exception as ue:
            logger.error(f"❌ Background logger error for trace {trace_id}: {ue}")
            await db.rollback()
