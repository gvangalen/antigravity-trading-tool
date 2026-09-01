from backend.services.asset_catalog_service import resolve_catalog_symbol, resolve_catalog_symbol_in_text


def test_stellar_resolves_to_the_canonical_xlm_symbol():
    assert resolve_catalog_symbol("Stellar") == "XLM"
    assert resolve_catalog_symbol_in_text("stellarindicatoren") == "XLM"
