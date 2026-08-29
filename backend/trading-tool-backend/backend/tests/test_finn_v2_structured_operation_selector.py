import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_structured_operation_selector_service import (
    FinnV2StructuredOperationSelectorService,
)


def _provider(**_kwargs):
    return {
        "parsed": {
            "operation_id": "evaluate_strategy",
            "confidence": 0.92,
            "entities": {"asset": "BTC"},
            "target_asset": None,
            "conversation_reference": None,
            "missing_inputs": [],
            "ambiguity_reason": None,
        }
    }


def test_structured_selector_can_only_choose_an_offered_contract():
    registry = FinnV2OperationRegistry()
    selection, error = FinnV2StructuredOperationSelectorService(provider=_provider).select(
        message="Beoordeel mijn strategie en bot.",
        candidate_contracts=(
            registry.get("evaluate_strategy"),
            registry.get("evaluate_bot"),
        ),
        facts={"entities": ("strategy", "bot")},
        verified_context=None,
    )

    assert error is None
    assert selection is not None
    assert selection.operation_id == "evaluate_strategy"


def test_structured_selector_rejects_a_provider_operation_outside_candidates():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "watchlist_add", "confidence": 0.9, "entities": {},
            "target_asset": None, "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Beoordeel mijn strategie.",
        candidate_contracts=(FinnV2OperationRegistry().get("evaluate_strategy"),),
        facts={},
        verified_context=None,
    )

    assert selection is None
    assert error == "selector_operation_outside_candidates"


def test_selector_provider_timeout_has_a_safe_operational_floor(monkeypatch):
    monkeypatch.setenv("FINN_V2_SELECTOR_TIMEOUT_SECONDS", "4")
    assert FinnV2StructuredOperationSelectorService._timeout_seconds() == 15


def test_selector_normalizes_structured_entity_transport_delimiters():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "explain_financial_concept", "confidence": 0.9,
            "entities": {"concept": "RSI},"}, "target_asset": None,
            "conversation_reference": None, "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Wat betekent RSI?",
        candidate_contracts=(FinnV2OperationRegistry().get("explain_financial_concept"),),
        facts={}, verified_context=None,
    )

    assert error is None
    assert selection.entities["concept"] == "RSI"


def test_selector_projects_catalog_assets_and_complete_setup_slots():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "create_setup", "confidence": 0.93,
            "entities": {
                "concept": None, "asset": "Polygon", "setup_id": None,
                "strategy_id": None, "bot_id": None, "setup_type": "breakout",
                "timeframe": "6H", "name": "Ripple Kompas",
            },
            "target_asset": "Polygon", "conversation_reference": None,
            "missing_inputs": ["timeframe", "name"], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Maak een setup.",
        candidate_contracts=(FinnV2OperationRegistry().get("create_setup"),),
        facts={"referenced_asset": "POL"}, verified_context=None,
    )

    assert error is None
    assert selection is not None
    assert selection.target_asset == "POL"
    assert selection.entities["asset"] == "POL"
    assert selection.entities["setup_type"] == "breakout"
    assert selection.entities["timeframe"] == "6H"
    assert selection.entities["name"] == "Ripple Kompas"
    assert selection.missing_inputs == ("timeframe", "name")


@pytest.mark.parametrize("asset", ("NEAR", "Cosmos", "Polygon", "UNI", "BTC"))
def test_selector_projects_explicit_catalog_asset_when_model_target_is_null(asset):
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "watchlist_add", "confidence": 0.95,
            "entities": {"concept": None, "asset": asset, "setup_id": None,
                         "strategy_id": None, "bot_id": None, "setup_type": None,
                         "timeframe": None, "name": None},
            "target_asset": None, "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message=f"Voeg {asset} toe.",
        candidate_contracts=(FinnV2OperationRegistry().get("watchlist_add"),),
        facts={"referenced_asset": asset}, verified_context=None,
    )

    assert error is None
    assert selection is not None
    assert selection.target_asset == selection.entities["asset"]
