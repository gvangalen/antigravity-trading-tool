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
