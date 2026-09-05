from backend.services.asset_catalog_service import resolve_catalog_symbol, resolve_catalog_symbol_in_text


def test_stellar_resolves_to_the_canonical_xlm_symbol():
    assert resolve_catalog_symbol("Stellar") == "XLM"
    assert resolve_catalog_symbol_in_text("stellarindicatoren") == "XLM"


def test_gold_resolves_to_the_canonical_xau_symbol_across_supported_languages():
    assert resolve_catalog_symbol("goud") == "XAU"
    assert resolve_catalog_symbol("Gold") == "XAU"
    assert resolve_catalog_symbol("or") == "XAU"


def test_stock_display_aliases_resolve_to_the_canonical_catalog_symbols():
    assert resolve_catalog_symbol("Apple") == "AAPL"
    assert resolve_catalog_symbol("Microsoft") == "MSFT"
