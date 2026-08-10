import importlib
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-32-plus-chars")

api = importlib.import_module("backend.api.ai_assistant_api")
score_api = importlib.import_module("backend.api.score_api")
assistant_module = importlib.import_module("backend.services.ai_assistant_service")
AiAssistantService = assistant_module.AiAssistantService
FinnPlanService = importlib.import_module("backend.services.finn_plan_service").FinnPlanService
state_repo_module = importlib.import_module("backend.infrastructure.repositories.conversation_state_repository")
ConversationStateRepository = state_repo_module.ConversationStateRepository
macro_catalog = importlib.import_module("backend.domain.macro_indicator_catalog")


def test_profile_capture_extracts_canonical_values():
    query = "Ik ben een swing trader en wil BTC volgen op 4H en 1D."

    assert api._looks_like_profile_capture(query) is True

    profile = api._extract_profile_update_from_query(query)

    assert profile["trader_types"] == ["swing_trader"]
    assert profile["primary_timeframes"] == ["4h", "1d"]
    assert profile["asset_focus"] == ["bitcoin"]


def test_profile_saved_envelope_uses_human_labels_not_internal_keys():
    envelope = api._build_profile_saved_envelope({
        "trader_types": ["swing_trader"],
        "primary_timeframes": ["4h", "1d"],
        "asset_focus": ["bitcoin"],
        "behavior_flags": ["fomo"],
    })

    response = envelope["response"].lower()

    assert "swing_trader" not in response
    assert "bitcoin" not in response
    assert "takes_profit_too_early" not in response
    assert "swing trader" in response
    assert "btc" in response
    assert "fomo" in response


def test_profile_explain_query_does_not_trigger_profile_capture():
    query = "Wat is mijn profiel en hoe gebruik je dat in je advies?"

    assert api._looks_like_profile_explain(query) is True
    assert api._looks_like_profile_capture(query) is False


def test_new_setup_creation_queries_do_not_force_legacy_setup_flow():
    assert api._should_prefer_legacy_setup_flow("Maak een setup voor BTC swing trading met daily trend en 4H entry.", {}) is False
    assert api._should_prefer_legacy_setup_flow("kan je een dca setup maken voor btc?", {}) is False
    assert api._should_prefer_legacy_setup_flow("Kun je voor BTC een swing setup bouwen met daily trend en 4H entry?", {}) is False
    assert api._should_prefer_legacy_setup_flow("Wat is mijn profiel?", {"current_flow": "setup_creation"}) is True


def test_setup_requests_use_modern_setup_flow_on_setup_page():
    assert api._should_use_modern_setup_creation_flow(
        "Kan je een dca setup maken voor BTC?",
        {"page": "setup"},
    ) is True
    assert api._should_use_modern_setup_creation_flow(
        "Maak een setup voor BTC swing trading met daily trend en 4H entry.",
        {"onboarding_step": "setup"},
    ) is True
    assert api._should_use_modern_setup_creation_flow(
        "Wat is mijn profiel?",
        {"current_flow": "setup_creation"},
    ) is True


def test_modern_transactional_state_record_is_not_treated_as_legacy_resume():
    state = {
        "current_flow": "strategy_creation",
        "slots": {
            "version": 2,
            "state_bucket": "transactional_state",
            "draft": {"draft_kind": "strategy"},
        },
    }

    assert api._is_legacy_transactional_flow_name("strategy_creation") is False
    assert api._is_modern_transactional_state_record(state) is True


def test_modern_transactional_flow_name_prefers_supported_active_flow():
    state = {
        "current_flow": "strategy_creation",
        "slots": {"draft": {"draft_kind": "strategy"}},
    }

    assert api._modern_transactional_flow_name(state, {}) == "strategy_creation"


def test_trading_stop_input_is_not_abort_like():
    assert assistant_module._looks_like_trading_stop_input("stop 88000") is True
    assert assistant_module._looks_like_trading_stop_input("entry 92000 target 98000 stop 88000") is True
    assert assistant_module._looks_like_trading_stop_input("annuleer dit") is False


def test_continue_transactional_follow_up_does_not_swallow_explicit_new_plan_request():
    class _Finn:
        def _looks_like_transactional_follow_up(self, query, draft):
            return True
        def looks_like_plan_request(self, query, draft):
            return "dca" in query.lower()
        def looks_like_strategy_request(self, query, context):
            return False
        def looks_like_bot_request(self, query, context):
            return False
        def looks_like_indicator_config_request(self, query, context):
            return False
        async def build_strategy_response_for_user(self, user_id, query, payload):
            return {"intent": "strategy_creation"}

    payload = {
        "current_flow": "strategy_creation",
        "finn_state": {"current_flow": "strategy_creation"},
        "finn_draft": {"draft_kind": "strategy", "setup_id": 1},
    }

    result = asyncio.run(api._continue_transactional_follow_up(
        _Finn(),
        12,
        "Maak een wekelijkse BTC DCA van 100 euro.",
        payload,
    ))

    assert result is None
    assert "finn_draft" not in payload
    assert "finn_state" not in payload


def test_score_api_payload_to_dict_supports_pydantic_v1_and_v2():
    class V1Payload:
        def dict(self):
            return {"value": 1}

    class V2Payload:
        def model_dump(self):
            return {"value": 2}

    assert score_api._payload_to_dict(V1Payload()) == {"value": 1}
    assert score_api._payload_to_dict(V2Payload()) == {"value": 2}


def test_watchlist_mutation_returns_action_card():
    envelope = api._build_watchlist_mutation_envelope(
        "Voeg BTC toe aan mijn watchlist.",
        {"symbol": "BTC"},
    )

    assert envelope["intent"] == "watchlist_mutation"
    assert envelope["actions"][0]["type"] == "add_to_watchlist"
    assert envelope["actions"][0]["symbol"] == "BTC"


def test_watchlist_mutation_is_not_detected_for_indicator_context():
    assert api._looks_like_watchlist_mutation(
        "Voeg SPY toe",
        {"mode": "indicator", "category": "macro", "symbol": "BTC"},
    ) is False


def test_indicator_configuration_request_detects_macro_context():
    assert api._looks_like_indicator_configuration_request(
        "SPY",
        {"mode": "indicator", "category": "macro"},
    ) is True


def test_all_active_macro_indicators_stay_in_indicator_flow_when_macro_context_is_present():
    active_macro_definitions = macro_catalog.get_active_macro_indicator_definitions()

    for definition in active_macro_definitions:
        indicator_name = definition["name"]
        display_name = definition["display_name"]
        context = {"mode": "indicator", "category": "macro", "symbol": "BTC"}

        assert api._looks_like_indicator_configuration_request(indicator_name, context) is True
        assert api._looks_like_indicator_configuration_request(display_name, context) is True
        assert api._looks_like_watchlist_mutation(f"Voeg {indicator_name} toe", context) is False
        assert api._looks_like_watchlist_mutation(f"Voeg {display_name} toe", context) is False


def test_ensure_pending_action_ids_registers_watchlist_action(monkeypatch):
    async def _fake_register(self, user_id, action_type, payload, trace_id=None, ttl_seconds=600):
        assert user_id == 42
        assert action_type == "add_to_watchlist"
        assert payload == {"symbol": "BTC"}
        return "act_watch_btc"

    monkeypatch.setattr(api.AiActionEngine, "register_pending_action", _fake_register)

    payload = asyncio.run(api._ensure_pending_action_ids(
        db=object(),
        user_id=42,
        response={
            "intent": "watchlist_mutation",
            "actions": [{"type": "add_to_watchlist", "symbol": "BTC", "label": "Voeg BTC toe"}],
        },
        locale="nl",
        trace_id="trace-watch",
    ))

    assert payload["can_confirm"] is True
    assert payload["actions"][0]["action_id"] == "act_watch_btc"
    assert payload["action"]["id"] == "act_watch_btc"


def test_ensure_pending_action_ids_turns_legacy_setup_draft_into_confirmable_action(monkeypatch):
    async def _fake_register(self, user_id, action_type, payload, trace_id=None, ttl_seconds=600):
        assert user_id == 7
        assert action_type == "setup"
        assert payload["symbol"] == "BTC"
        assert payload["setup_type"] == "trade"
        return "act_setup_btc"

    monkeypatch.setattr(api.AiActionEngine, "register_pending_action", _fake_register)

    payload = asyncio.run(api._ensure_pending_action_ids(
        db=object(),
        user_id=7,
        response={
            "response": "Je setup staat klaar.",
            "draft": {
                "type": "setup",
                "payload": {
                    "name": "BTC Trade 4H",
                    "symbol": "BTC",
                    "setup_type": "trade",
                    "timeframe": "4H",
                },
            },
            "actions": [],
        },
        locale="nl",
        trace_id="trace-setup",
    ))

    assert payload["can_confirm"] is True
    assert payload["actions"][0]["type"] == "setup"
    assert payload["actions"][0]["action_id"] == "act_setup_btc"
    assert payload["actions"][0]["label"] == "Setup opslaan"


def test_finalize_legacy_response_returns_confirmable_action_payload(monkeypatch):
    class _Service:
        def _classify_intent(self, query):
            return "setup_creation"

    class _Finn:
        def _build_response_analysis_metadata(self, response, context_payload, route_source="legacy"):
            return response

        def _response_mode_for_flow(self, flow, draft):
            return "transactional"

    async def _fake_register(self, user_id, action_type, payload, trace_id=None, ttl_seconds=600):
        assert user_id == 7
        assert action_type == "setup"
        return "act_setup_final"

    monkeypatch.setattr(api.AiActionEngine, "register_pending_action", _fake_register)
    monkeypatch.setattr(api, "_log_finn_prompt_audit", lambda **kwargs: None)
    monkeypatch.setattr(api, "_record_finn_product_event", lambda **kwargs: {})
    monkeypatch.setattr(api, "_record_behavioral_response_events", lambda **kwargs: None)

    result = asyncio.run(api._finalize_legacy_response(
        service=_Service(),
        response="Je setup staat klaar.",
        action=None,
        draft={
            "type": "setup",
            "payload": {
                "name": "BTC Trade 4H",
                "symbol": "BTC",
                "setup_type": "trade",
                "timeframe": "4H",
            },
        },
        state={"current_flow": "setup_creation", "missing_slots": ["timeframe"], "next_question": "timeframe"},
        reasoning=None,
        suggested_actions=["Opslaan"],
        session_id="sess-1",
        finn=_Finn(),
        user_id=7,
        trace_id="trace-legacy-final",
        db=object(),
        query="Maak een setup voor BTC.",
        context_payload={"locale": "nl"},
        started_at=0.0,
    ))

    assert result.can_confirm is True
    assert result.actions[0]["action_id"] == "act_setup_final"
    assert result.action["type"] == "setup"
    assert result.draft["type"] == "setup"
    assert result.missing_fields == ["timeframe"]
    assert result.next_question == "timeframe"


def test_setup_strategy_listing_detection_matches_real_prompt():
    assert api._looks_like_setup_strategy_listing_request("Laat mijn actieve setups en strategieën zien.") is True


def test_assistant_context_preserves_explicit_finn_subject_type():
    from backend.schemas.assistant_schema import AssistantContextSchema

    context = AssistantContextSchema(
        page="/setup",
        symbol="BTC",
        setup_id=62,
        strategy_id=257,
        finn_subject_type="plan",
        locale="en",
    )

    payload = api._assistant_context_payload(context)

    assert payload["finn_subject_type"] == "plan"
    assert payload["locale"] == "en"


def test_explicit_request_locale_wins_over_stale_account_locale(monkeypatch):
    async def _get_user(_self, _user_id):
        return SimpleNamespace(ai_preferences={"locale": "nl"})

    monkeypatch.setattr(api.UserRepository, "get_by_id", _get_user)

    payload = asyncio.run(api._enrich_with_trader_profile(
        object(),
        7,
        {"page": "/setup", "locale": "en", "finn_subject_type": "plan"},
        query="Review this plan",
    ))

    assert payload["locale"] == "en"
    assert payload["finn_subject_type"] == "plan"


def test_transactional_legacy_state_does_not_get_rescued_into_general_help():
    class _Finn:
        def looks_like_general_capability_request(self, query): return False
        def looks_like_product_refresh_help_request(self, query): return False
        def looks_like_product_help_request(self, query, context): return True
        def looks_like_education_request(self, query): return False
        def looks_like_plan_adherence_review_request(self, query): return False
        def looks_like_outcome_tracking_request(self, query): return False
        def looks_like_governed_action_review_request(self, query, context): return False
        def looks_like_outcome_memory_request(self, query): return False
        def looks_like_personal_performance_request(self, query): return False
        def looks_like_trade_journal_intelligence_request(self, query): return False
        def looks_like_personal_coach_request(self, query): return False
        def looks_like_portfolio_intelligence_request(self, query, context): return False
        def looks_like_priority_engine_request(self, query, context): return False
        def looks_like_portfolio_operating_system_request(self, query): return False
        def looks_like_decision_review_request(self, query, context): return False
        def looks_like_ultra_implicit_review_prompt(self, query): return False
        def looks_like_mission_control_explain_request(self, query, context): return False
        def looks_like_entity_explain_request(self, query, context): return False
        def looks_like_behavioral_intelligence_request(self, query): return False
        def looks_like_weekly_reflection_request(self, query): return False
        def looks_like_behavioral_memory_request(self, query): return False
        def looks_like_finn_report_request(self, query): return False
        def looks_like_daily_coach_request(self, query): return False
        def looks_like_indicator_insight_request(self, query): return False
        def looks_like_status_request(self, query): return False

    assert api._legacy_response_needs_finn_rescue(
        _Finn(),
        "Maak een setup voor BTC.",
        {},
        response_text="Wil je een DCA of een actieve Trade setup maken?",
        action=None,
        draft=None,
        state={"current_flow": "setup_creation", "status": "collecting", "slots": {"symbol": "BTC"}},
    ) is False


class _FakeStateRepo:
    def __init__(self):
        self.saved = []
        self.cleared = []
        self.session = SimpleNamespace()

    async def save_state(self, user_id, flow_name, asset_val, slots):
        self.saved.append((user_id, flow_name, asset_val, dict(slots)))

    async def clear_state(self, user_id):
        self.cleared.append(user_id)


class _FakeSetupRepo:
    def __init__(self, setups):
        self._setups = setups

    async def get_all_setups(self, user_id):
        return list(self._setups)


class _FakeStrategyRepo:
    def __init__(self, strategies):
        self._strategies = strategies

    async def query_strategies(self, user_id, filters):
        symbol = (filters or {}).get("symbol")
        if not symbol:
            return list(self._strategies)
        return [row for row in self._strategies if row.get("symbol") == symbol]


class _FakeResult:
    def __init__(self, row):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, query, params):
        return _FakeResult(self._row)


def test_deterministic_pre_parse_marks_trading_prompt_as_trade_setup():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "Maak een setup voor BTC swing trading met daily trend en 4H entry.",
            None,
            "BTC",
            12,
        )
    )

    assert conv_state["current_flow"] == "setup_creation"
    assert conv_state["slots"]["symbol"] == "BTC"
    assert conv_state["slots"]["setup_type"] == "trade"
    assert "dca_frequency" not in conv_state["slots"]


def test_explicit_setup_request_overrides_stale_general_help_state():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "Maak een setup voor BTC swing trading met daily trend en 4H entry.",
            {"current_flow": "general_help", "slots": {}, "status": "collecting"},
            "BTC",
            13,
        )
    )

    assert conv_state["current_flow"] == "setup_creation"
    assert conv_state["slots"]["symbol"] == "BTC"
    assert conv_state["slots"]["setup_type"] == "trade"


def test_deterministic_flow_turn_asks_next_setup_question_without_llm():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=21,
            user_query="Maak een setup voor BTC.",
            conv_state={
                "current_flow": "setup_creation",
                "slots": {"symbol": "BTC"},
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert response == "Wil je een DCA of een actieve Trade setup maken?"
    assert action is None
    assert draft is None
    assert state["current_flow"] == "setup_creation"
    assert state["missing_slots"][0] == "setup_type"
    assert suggested_actions is None


def test_deterministic_pre_parse_bootstraps_natural_language_dca_setup_request():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "Kan je een DCA setup maken voor BTC?",
            None,
            "BTC",
            77,
        )
    )

    assert conv_state["current_flow"] == "setup_creation"
    assert conv_state["slots"]["symbol"] == "BTC"
    assert conv_state["slots"]["setup_type"] == "dca"


def test_deterministic_flow_turn_keeps_dca_setup_in_same_flow_after_frequency_answer():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=78,
            user_query="elke week",
            conv_state={
                "current_flow": "setup_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_type": "dca",
                    "dca_frequency": "weekly",
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "Welke timeframe" in response
    assert action is None
    assert draft is None
    assert state["current_flow"] == "setup_creation"
    assert state["missing_slots"][0] == "timeframe"
    assert state["next_question"] == "timeframe"
    assert suggested_actions is None


def test_deterministic_flow_turn_advances_to_name_after_timeframe_for_dca_setup():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=79,
            user_query="1D",
            conv_state={
                "current_flow": "setup_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_type": "dca",
                    "timeframe": "1D",
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "Welke naam" in response
    assert action is None
    assert draft is None
    assert state["next_question"] == "name"
    assert suggested_actions is None


def test_deterministic_pre_parse_accepts_default_macro_threshold_reply():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "standaard is goed",
            {
                "current_flow": "setup_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_type": "dca",
                    "timeframe": "1D",
                    "name": "Bitcoin test DCA",
                    "dca_frequency": "weekly",
                    "dca_day": "monday",
                },
                "status": "collecting",
            },
            "BTC",
            91,
        )
    )

    assert conv_state["slots"]["market_condition"] == "balanced_pullback"
    assert conv_state["slots"]["min_macro_score"] == 30
    assert conv_state["slots"]["max_macro_score"] == 70
    assert conv_state["slots"]["min_technical_score"] == 40
    assert conv_state["slots"]["max_technical_score"] == 80
    assert conv_state["slots"]["min_market_score"] == 20
    assert conv_state["slots"]["max_market_score"] == 60


def test_deterministic_pre_parse_maps_confirmed_strength_market_condition():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "alleen bij bevestigd sterk",
            {
                "current_flow": "setup_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_type": "trade",
                    "timeframe": "4H",
                    "name": "BTC swing setup",
                },
                "status": "collecting",
            },
            "BTC",
            92,
        )
    )

    assert conv_state["slots"]["market_condition"] == "confirmed_strength"
    assert conv_state["slots"]["min_macro_score"] == 40
    assert conv_state["slots"]["max_macro_score"] == 100
    assert conv_state["slots"]["min_technical_score"] == 55
    assert conv_state["slots"]["max_technical_score"] == 100
    assert conv_state["slots"]["min_market_score"] == 35
    assert conv_state["slots"]["max_market_score"] == 100


def test_legacy_profile_overlay_is_suppressed_during_transactional_setup_flow():
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=_FakeStateRepo(),
        ai_gateway=None,
    )

    result = assistant._apply_legacy_profile_overlay(
        "Welke timeframe wil je gebruiken?",
        intent="general_help",
        context_data={
            "current_flow": "setup_creation",
            "trader_profile_used": True,
            "trader_profile": {"behavior_flags": ["holds_losers_too_long"]},
        },
        resolved_symbol="BTC",
    )

    assert result == "Welke timeframe wil je gebruiken?"


def test_deterministic_flow_turn_finishes_setup_without_llm_when_slots_complete():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=22,
            user_query="wekelijks",
            conv_state={
                "current_flow": "setup_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_type": "dca",
                    "timeframe": "1W",
                    "name": "BTC DCA",
                    "dca_frequency": "weekly",
                    "dca_day": "monday",
                    "market_condition": "balanced_pullback",
                    "min_macro_score": 30,
                    "max_macro_score": 70,
                    "min_technical_score": 40,
                    "max_technical_score": 80,
                    "min_market_score": 20,
                    "max_market_score": 60,
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "staat klaar" in response
    assert action is None
    assert draft["type"] == "setup"
    assert draft["payload"]["symbol"] == "BTC"
    assert draft["payload"]["setup_type"] == "dca"
    assert draft["payload"]["timeframe"] == "1W"
    assert draft["payload"]["name"] == "BTC DCA"
    assert draft["payload"]["dca_frequency"] == "weekly"
    assert draft["payload"]["dca_day"] == "monday"
    assert draft["payload"]["min_macro_score"] == 30
    assert state["current_flow"] == "none"
    assert state_repo.cleared == [22]
    assert suggested_actions == ["Opslaan", "Pas aan"]


def test_trade_setup_prompt_parses_entry_timeframe_and_builds_trade_draft():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "Maak een setup voor BTC swing trading met daily trend en 4H entry.",
            None,
            "BTC",
            44,
        )
    )

    assert conv_state["slots"]["setup_type"] == "trade"
    assert conv_state["slots"]["timeframe"] == "4H"

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=44,
            user_query="Maak een setup voor BTC swing trading met daily trend en 4H entry.",
            conv_state={
                "current_flow": "setup_creation",
                "slots": conv_state["slots"],
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "Welke naam" in response
    assert action is None
    assert draft is None
    assert state["current_flow"] == "setup_creation"
    assert state["next_question"] == "name"
    assert suggested_actions is None


def test_explicit_finalize_does_not_complete_incomplete_setup_flow():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "maak de setup",
            {
                "current_flow": "setup_creation",
                "slots": {"symbol": "BTC", "setup_type": "dca"},
                "status": "collecting",
            },
            "BTC",
            90,
        )
    )

    assert conv_state["status"] == "collecting"
    assert conv_state["current_flow"] == "setup_creation"


def test_deterministic_flow_turn_asks_next_strategy_question_without_llm():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=23,
            user_query="voor mijn setup BTC Swing Blueprint",
            conv_state={
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_id": 258,
                    "setup_type": "dca",
                    "timeframe": "1W",
                    "setup_name": "Bitcoin test DCA",
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "bedrag" in response.lower() or "uitvoering" in response.lower()
    assert action is None
    assert draft is None
    assert state["current_flow"] == "strategy_creation"
    assert state["next_question"] == "base_amount_eur"
    assert state["missing_slots"] == ["base_amount_eur", "execution_mode", "risk_profile"]
    assert suggested_actions is None


def test_deterministic_flow_turn_builds_strategy_draft_when_required_slots_present():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )
    assistant._active_preferences = {"locale": "nl", "experience_level": "beginner"}

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=24,
            user_query="100",
            conv_state={
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_id": 258,
                    "setup_type": "dca",
                    "timeframe": "1W",
                    "setup_name": "Bitcoin test DCA",
                    "base_amount_eur": 100,
                    "execution_mode": "manual",
                    "risk_profile": "balanced",
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert "staat klaar" in response
    assert action is None
    assert draft["type"] == "strategy"
    assert draft["payload"]["name"] == "Bitcoin test DCA strategie"
    assert draft["payload"]["setup_id"] == 258
    assert draft["payload"]["timeframe"] == "1W"
    assert draft["payload"]["base_amount"] == 100
    assert draft["payload"]["base_amount_eur"] == 100
    assert draft["payload"]["execution_mode"] == "manual"
    assert draft["payload"]["risk_profile"] == "balanced"
    assert state["current_flow"] == "none"
    assert state_repo.cleared == [24]
    assert suggested_actions == ["Opslaan", "Pas aan"]


def test_strategy_follow_up_accepts_plain_numeric_amount_without_euro_keyword():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "100",
            {
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_id": 258,
                    "setup_type": "dca",
                    "timeframe": "1W",
                },
                "status": "collecting",
                "next_question": "strategy.base_amount_eur",
            },
            "BTC",
            91,
        )
    )

    assert conv_state["current_flow"] == "strategy_creation"
    assert conv_state["slots"]["base_amount_eur"] == 100
    assert conv_state["slots"]["base_amount"] == 100
    assert assistant._get_missing_flow_slots("strategy_creation", conv_state["slots"]) == [
        "execution_mode",
        "risk_profile",
    ]


def test_deterministic_flow_turn_moves_to_execution_mode_after_amount_is_known():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=25,
            user_query="gebruik 100 euro per uitvoering",
            conv_state={
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_id": 258,
                    "setup_type": "dca",
                    "timeframe": "1W",
                    "setup_name": "Bitcoin test DCA",
                    "base_amount_eur": 100,
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert action is None
    assert draft is None
    assert state["current_flow"] == "strategy_creation"
    assert state["next_question"] == "execution_mode"
    assert "basisbedrag" not in response.lower()
    assert "handmatig" in response.lower() or "automatisch" in response.lower()


def test_deterministic_flow_turn_keeps_known_setup_and_skips_setup_question():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=None,
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=None,
        state_repo=state_repo,
        ai_gateway=None,
    )

    response, action, draft, state, suggested_actions = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=251,
            user_query="maak een strategie voor mijn btc dca setup",
            conv_state={
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                    "setup_id": 258,
                    "setup_type": "dca",
                    "timeframe": "1W",
                    "setup_name": "Bitcoin test DCA",
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert action is None
    assert draft is None
    assert state["current_flow"] == "strategy_creation"
    assert state["next_question"] == "base_amount_eur"
    assert "welke setup" not in response.lower()
    assert "bedrag" in response.lower() or "uitvoering" in response.lower()


def test_deterministic_pre_parse_rehydrates_stale_strategy_flow_before_amount_question():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=_FakeSetupRepo([
            {
                "id": 258,
                "symbol": "BTC",
                "setup_type": "dca",
                "timeframe": "1W",
                "name": "Bitcoin test DCA",
            }
        ]),
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=_FakeStrategyRepo([]),
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "maak een strategie voor btc",
            {
                "current_flow": "strategy_creation",
                "slots": {
                    "symbol": "BTC",
                },
                "status": "collecting",
            },
            "BTC",
            111,
        )
    )

    assert conv_state["current_flow"] == "strategy_creation"
    assert conv_state["slots"]["setup_id"] == 258
    assert conv_state["slots"]["setup_type"] == "dca"
    assert conv_state["slots"]["timeframe"] == "1W"
    assert conv_state["slots"]["setup_name"] == "Bitcoin test DCA"
    assert state_repo.saved[-1][1] == "strategy_creation"
    assert state_repo.saved[-1][3]["setup_id"] == 258


def test_deterministic_pre_parse_rehydrates_stale_bot_flow_before_budget_questions():
    state_repo = _FakeStateRepo()
    assistant = AiAssistantService(
        score_repo=None,
        setup_repo=_FakeSetupRepo([]),
        report_repo=None,
        bot_repo=None,
        user_repo=None,
        market_data_repo=None,
        strategy_repo=_FakeStrategyRepo([
            {
                "id": 801,
                "symbol": "BTC",
                "name": "BTC DCA strategie",
                "timeframe": "1W",
                "base_amount": 100,
            }
        ]),
        state_repo=state_repo,
        ai_gateway=None,
    )

    conv_state = asyncio.run(
        assistant._deterministic_pre_parse_slots(
            "start een bot voor btc",
            {
                "current_flow": "bot_creation",
                "slots": {
                    "symbol": "BTC",
                    "name": "BTC Bot",
                },
                "status": "collecting",
            },
            "BTC",
            112,
        )
    )

    assert conv_state["current_flow"] == "bot_creation"
    assert conv_state["slots"]["strategy_id"] == 801
    assert conv_state["slots"]["strategy_name"] == "BTC DCA strategie"
    assert conv_state["slots"]["timeframe"] == "1W"
    assert conv_state["slots"]["base_amount"] == 100
    assert conv_state["slots"]["base_amount_eur"] == 100
    assert state_repo.saved[-1][1] == "bot_creation"
    assert state_repo.saved[-1][3]["strategy_id"] == 801


def test_conversation_state_repo_restores_collecting_status_from_saved_flow():
    repo = ConversationStateRepository(
        _FakeSession({
            "current_flow": "setup_creation",
            "asset": "BTC",
            "slots": {"symbol": "BTC", "setup_type": "trade"},
            "updated_at": "2026-07-02T15:00:00Z",
        })
    )

    state = asyncio.run(repo.get_state(55))

    assert state["current_flow"] == "setup_creation"
    assert state["status"] == "collecting"
    assert state["slots"]["setup_type"] == "trade"
