import importlib
import asyncio
import os
from types import SimpleNamespace

os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-32-plus-chars")

api = importlib.import_module("backend.api.ai_assistant_api")
score_api = importlib.import_module("backend.api.score_api")
assistant_module = importlib.import_module("backend.services.ai_assistant_service")
AiAssistantService = assistant_module.AiAssistantService


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


def test_setup_creation_queries_prefer_legacy_setup_flow():
    assert api._should_prefer_legacy_setup_flow("Maak een setup voor BTC swing trading met daily trend en 4H entry.", {}) is True
    assert api._should_prefer_legacy_setup_flow("kan je een dca setup maken voor btc?", {}) is True
    assert api._should_prefer_legacy_setup_flow("Wat is mijn profiel?", {"current_flow": "setup_creation"}) is True


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


def test_setup_strategy_listing_detection_matches_real_prompt():
    assert api._looks_like_setup_strategy_listing_request("Laat mijn actieve setups en strategieën zien.") is True


class _FakeStateRepo:
    def __init__(self):
        self.saved = []
        self.cleared = []
        self.session = SimpleNamespace()

    async def save_state(self, user_id, flow_name, asset_val, slots):
        self.saved.append((user_id, flow_name, asset_val, dict(slots)))

    async def clear_state(self, user_id):
        self.cleared.append(user_id)


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
    assert draft["payload"]["dca_frequency"] == "weekly"
    assert state["current_flow"] == "none"
    assert state_repo.cleared == [22]
    assert suggested_actions == ["Opslaan", "Pas aan"]
