import importlib
import os


os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-with-32-plus-chars")

api = importlib.import_module("backend.api.ai_assistant_api")


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
