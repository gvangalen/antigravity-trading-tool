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


def test_finn_plan_service_routes_modern_setup_prompts_into_plan_creation():
    service = FinnPlanService(None)

    assert service.looks_like_plan_request("Kan je een dca setup maken voor BTC?") is True
    assert service.looks_like_plan_request("Maak een setup voor BTC swing trading met daily trend en 4H entry.") is True
    assert service.looks_like_plan_request("Maak een wekelijkse BTC DCA van 100 euro.") is True


def test_modern_transactional_state_record_is_not_treated_as_legacy_resume():
    state = {
        "current_flow": "strategy_creation",
        "slots": {
            "version": 2,
            "state_bucket": "transactional_state",
            "draft": {"draft_kind": "strategy"},
        },
    }

    assert api._is_legacy_transactional_flow_name("strategy_creation") is True
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
    assert state["missing_slots"] == ["timeframe"]
    assert state["next_question"] == "timeframe"
    assert suggested_actions is None


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
                    "dca_frequency": "weekly",
                    "market_condition": "neutral",
                    "name": "BTC DCA",
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
    assert draft["payload"]["dca_frequency"] == "weekly"
    assert "min_macro_score" not in draft["payload"]
    assert "dca_day" not in draft["payload"]
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

    assert "staat klaar" in response
    assert action is None
    assert draft["type"] == "setup"
    assert draft["payload"]["setup_type"] == "trade"
    assert draft["payload"]["timeframe"] == "4H"
    assert draft["payload"]["name"] == "BTC Trade 4H"
    assert "market_condition" not in draft["payload"]
    assert state["current_flow"] == "none"
    assert suggested_actions == ["Opslaan", "Pas aan"]


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


def test_deterministic_flow_turn_ignores_modern_strategy_flow_state():
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

    result = asyncio.run(
        assistant._build_deterministic_flow_turn(
            user_id=23,
            user_query="voor mijn setup BTC Swing Blueprint",
            conv_state={
                "current_flow": "strategy_creation",
                "slots": {
                    "draft": {"draft_kind": "strategy"},
                    "state_bucket": "transactional_state",
                    "version": 2,
                },
                "status": "collecting",
            },
            resolved_symbol="BTC",
        )
    )

    assert result is None


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
