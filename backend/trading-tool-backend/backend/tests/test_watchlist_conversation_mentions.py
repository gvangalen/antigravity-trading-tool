import asyncio

from backend.services.watchlist_conversation_service import asset_mentions, replacement_mentions
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor


CATALOG = {
    "BTC": {"display_name": "Bitcoin", "asset_class": "crypto", "aliases": []},
    "ETH": {"display_name": "Ethereum", "asset_class": "crypto", "aliases": ["Ether"]},
    "AAPL": {"display_name": "Apple Inc.", "asset_class": "stock", "aliases": ["Apple"]},
    "XYZ": {"display_name": "Xylophone", "asset_class": "crypto", "aliases": []},
}


def test_mentions_are_catalog_driven_and_preserve_explicit_pair():
    result = asset_mentions("Verwijder Apple en voeg BTC/EUR toe aan mijn watchlist", CATALOG)
    assert [(item["symbol"], item["quote_currency"]) for item in result] == [
        ("AAPL", None), ("BTC", "EUR"),
    ]
    assert [item["symbol"] for item in asset_mentions("Voeg Ether toe", CATALOG)] == ["ETH"]
    assert [item["symbol"] for item in asset_mentions("Volg Xylophone", CATALOG)] == ["XYZ"]


def test_unknown_asset_is_not_guessed():
    assert asset_mentions("Voeg onbekende munt toe", CATALOG) == []


def test_replacement_direction_comes_from_words_and_catalog_mentions():
    for text in (
        "Apple niet meer volgen; volg Bitcoin",
        "Haal Apple weg en voeg BTC/EUR toe",
        "Nee, ik wil in plaats van Apple voortaan Bitcoin volgen",
    ):
        result = replacement_mentions(text, CATALOG)
        assert (result["source"]["symbol"], result["target"]["symbol"]) == ("AAPL", "BTC")
    reverse = replacement_mentions("Voeg BTC toe in plaats van Apple", CATALOG)
    assert (reverse["source"]["symbol"], reverse["target"]["symbol"]) == ("AAPL", "BTC")
    assert replacement_mentions("Vergelijk Apple met Bitcoin", CATALOG) is None


def test_responses_front_door_routes_replacements_through_action_contract():
    async def exercise():
        front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="replacement-test")
        cases = (
            ("Apple niet meer volgen; volg Bitcoin", "BTC", None, ["quote_currency"]),
            ("Verwijder Apple en voeg BTC/EUR toe aan de watchlist", "BTC", "EUR", []),
            ("Verwijder Apple en voeg ETH toe aan de watchlist", "ETH", None, ["quote_currency"]),
        )
        for message, asset, quote, missing in cases:
            result = await front.run(message=message, instructions="", conversation_context={}, verified_asset="AAPL")
            assert result.proposal_analysis.request_plan.operation_id == "watchlist_add"
            state = result.proposal_analysis.request_plan.operation_state
            assert state["collected_inputs"]["asset"] == asset
            assert state["collected_inputs"].get("quote_currency") == quote
            assert state["missing_required_inputs"] == missing
        ambiguous = await front.run(
            message="Haal Apple weg en voeg BTC/EUR toe", instructions="",
            conversation_context={}, verified_asset="AAPL",
        )
        assert ambiguous.proposal_analysis is None
        assert "watchlist" in ambiguous.response.text
        assert "portfolio" in ambiguous.response.text

    asyncio.run(exercise())
