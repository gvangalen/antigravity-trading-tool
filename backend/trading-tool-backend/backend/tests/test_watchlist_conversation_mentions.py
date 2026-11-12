import asyncio

from backend.services.watchlist_conversation_service import ambiguous_asset_change_scope, asks_for_watchlist_inventory, asset_mentions, replacement_mentions
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier


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


def test_repeated_asset_names_keep_a_consistent_directed_replacement():
    cases = (
        ("Ik wil in plaats van Apple voortaan Bitcoin volgen. Vervang Apple in mijn watchlist door Bitcoin.", "AAPL", "BTC", None),
        ("Vervang Apple in mijn watchlist door BTC/EUR.", "AAPL", "BTC", "EUR"),
        ("Replace Ether with Apple. I want Apple instead of Ethereum.", "ETH", "AAPL", None),
    )
    for message, source, target, quote in cases:
        result = replacement_mentions(message, CATALOG)
        assert result is not None
        assert (result["source"]["symbol"], result["target"]["symbol"]) == (source, target)
        assert result["target"]["quote_currency"] == quote

    assert replacement_mentions("Vervang Apple door Bitcoin. Vervang Bitcoin door Apple.", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Bitcoin en vervang Bitcoin door Apple", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Bitcoin en Bitcoin door Apple", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Apple en BTC", CATALOG) is None
    assert replacement_mentions("Vervang Apple en BTC door Apple", CATALOG) is None
    assert replacement_mentions("Vervang Apple niet door BTC/EUR in mijn watchlist.", CATALOG) is None
    assert replacement_mentions("BTC/EUR staat al in mijn watchlist. Vervang Apple door Bitcoin.", CATALOG)["target"]["quote_currency"] is None
    assert replacement_mentions("Vervang Apple door BTC/EUR. Vervang Apple door BTC/USDT.", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Bitcoin. Volg ook Ether.", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Bitcoin in mijn watchlist. Verwijder Bitcoin uit mijn watchlist.", CATALOG) is None
    assert replacement_mentions("Vervang Apple door Bitcoin in mijn watchlist. Voeg BTC/EUR toe aan mijn watchlist.", CATALOG) is None


def test_responses_front_door_routes_replacements_through_action_contract():
    async def exercise():
        front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="replacement-test")
        cases = (
            ("Apple niet meer volgen; volg Bitcoin", "BTC", None, ["quote_currency"]),
            ("Ik wil in plaats van Apple voortaan Bitcoin volgen. Vervang Apple in mijn watchlist door Bitcoin.", "BTC", None, ["quote_currency"]),
            ("BTC/EUR staat al in mijn watchlist. Vervang Apple door Bitcoin.", "BTC", None, ["quote_currency"]),
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


def test_single_catalog_asset_with_ambiguous_change_asks_scope_before_any_action():
    for message in (
        "Ik wil mijn aandeel aanpassen in bitcoin.",
        "Ik wil mijn aandeel aanpassen in Ethereum.",
        "I want to change my stock into Apple.",
    ):
        assert ambiguous_asset_change_scope(message, CATALOG)
    assert not ambiguous_asset_change_scope("Voeg Bitcoin toe aan mijn watchlist", CATALOG)
    assert not ambiguous_asset_change_scope("Ik wil mijn portfolio aanpassen in Ethereum", CATALOG)
    assert not ambiguous_asset_change_scope("Ik wil mijn aandeel aanpassen in onbekende munt", CATALOG)

    async def exercise():
        front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="ambiguous-asset-change")
        result = await front.run(
            message="Ik wil mijn aandeel aanpassen in bitcoin.", instructions="",
            conversation_context={}, verified_asset="AAPL",
        )
        assert result.proposal_analysis is None
        assert result.response.text == "Bedoel je een wijziging in je watchlist of je portfolio?"

    asyncio.run(exercise())


def test_explicit_watchlist_inventory_reads_owner_entries_without_a_selected_asset():
    assert asks_for_watchlist_inventory("Welke assets staan op mijn watchlist?")
    assert asks_for_watchlist_inventory("Show my watchlist")
    assert not asks_for_watchlist_inventory("Wat vind je van mijn watchlist?")
    assert not asks_for_watchlist_inventory("Voeg ETH toe aan mijn watchlist")

    async def exercise():
        front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=7, run_id="inventory-test")

        async def read(call):
            assert call.read_tools == ("read_watchlist",)
            assert call.inputs == {}
            return {"status": "completed", "results": [{
                "scope": "read_watchlist", "status": "completed",
                "data": {"symbols": [
                    {"symbol": "BTC", "quote_currency": "USDT", "pair": "BTC/USDT"},
                    {"symbol": "ETH", "quote_currency": "EUR", "pair": "ETH/EUR"},
                    {"symbol": "AAPL", "quote_currency": None, "pair": None},
                ]},
            }]}

        front.reads = read
        result = await front.run(
            message="Welke assets staan op mijn watchlist?", instructions="",
            conversation_context={}, verified_asset=None,
        )
        assert result.proposal_analysis is None
        assert result.response.answer_kind == "watchlist_inventory"
        verified = await FinnResponsesAnswerVerifier().verify(
            message="Welke assets staan op mijn watchlist?", result=result.response, locale="nl",
        )
        assert verified.status == "completed", verified.reason
        assert verified.text == "Op je watchlist staan: BTC/USDT, ETH/EUR, AAPL."

    asyncio.run(exercise())
