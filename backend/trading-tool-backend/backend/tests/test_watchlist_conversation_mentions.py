from backend.services.watchlist_conversation_service import asset_mentions


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
