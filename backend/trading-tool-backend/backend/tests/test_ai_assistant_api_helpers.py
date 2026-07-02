import importlib
import os


os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-32-plus-chars")

api = importlib.import_module("backend.api.ai_assistant_api")
score_api = importlib.import_module("backend.api.score_api")


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
