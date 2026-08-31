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
    assert selection.entities["setup_type"] == "trade"
    assert selection.entities["timeframe"] == "6H"
    assert selection.entities["name"] == "Ripple Kompas"
    assert selection.missing_inputs == ("timeframe", "name")


def test_selector_projects_natural_setup_entities_through_the_canonical_catalog():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "create_setup", "confidence": 0.93,
            "entities": {"concept": None, "asset": "Solana", "setup_id": None,
                         "strategy_id": None, "bot_id": None, "setup_type": "swingtrade",
                         "timeframe": "vieruursgrafiek", "name": "SOL Beheerste Uitbraak"},
            "target_asset": "Solana", "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Werk een swingtrade voor Solana uit op de vier-uursgrafiek.",
        candidate_contracts=(FinnV2OperationRegistry().get("create_setup"),),
        facts={"referenced_asset": "SOL"}, verified_context=None,
    )

    assert error is None
    assert selection.entities["setup_type"] == "trade"
    assert selection.entities["timeframe"] == "4H"
    assert selection.entities["asset"] == "SOL"


def test_selector_projects_contextual_action_reference_only_for_matching_registry_input():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "activate_bot", "confidence": 0.95,
            "entities": {"concept": None, "asset": None, "setup_id": None,
                         "strategy_id": None, "bot_id": "170", "setup_type": None,
                         "timeframe": None, "name": None},
            "target_asset": None, "conversation_reference": "previous_verified_response",
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    registry = FinnV2OperationRegistry()
    selection, error = selector.select(
        message="Laat die bot live handelen.",
        candidate_contracts=(registry.get("activate_bot"),), facts={},
        verified_context={"last_verified_context": {"resolved_entities": {"bot_id": 170}}},
    )

    assert error is None
    assert selection.conversation_reference == "previous_verified_response"


def test_selector_projects_matching_contextual_reference_when_provider_omits_telemetry():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "activate_bot", "confidence": 0.95,
            "entities": {"concept": None, "asset": None, "setup_id": None,
                         "strategy_id": None, "bot_id": "170", "setup_type": None,
                         "timeframe": None, "name": None},
            "target_asset": None, "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Laat die gekoppelde bot live handelen.",
        candidate_contracts=(FinnV2OperationRegistry().get("activate_bot"),), facts={},
        verified_context={"last_verified_context": {"resolved_entities": {"bot_id": 170}}},
    )

    assert error is None
    assert selection is not None
    assert selection.conversation_reference == "previous_verified_response"


def test_selector_canonicalizes_descriptive_setup_type_phrases():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "create_setup", "confidence": 0.95,
            "entities": {"concept": None, "asset": "ETH", "setup_id": None,
                         "strategy_id": None, "bot_id": None, "setup_type": "weekly breakout",
                         "timeframe": "1W", "name": "Rustige Doorbraak"},
            "target_asset": "ETH", "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Werk een setup uit.",
        candidate_contracts=(FinnV2OperationRegistry().get("create_setup"),), facts={}, verified_context=None,
    )

    assert error is None
    assert selection is not None
    assert selection.entities["setup_type"] == "trade"


def test_selector_projects_create_setup_slots_from_explicit_typed_input_not_raw_telemetry():
    selector = FinnV2StructuredOperationSelectorService(
        provider=lambda **_kwargs: {"parsed": {
            "operation_id": "create_setup", "confidence": 0.95,
            "entities": {"concept": "DCA", "asset": "ETH", "setup_id": None,
                         "strategy_id": None, "bot_id": None, "setup_type": "investment",
                         "timeframe": "1D", "name": "ETH Spreiding"},
            "target_asset": "ETH", "conversation_reference": None,
            "missing_inputs": [], "ambiguity_reason": None,
        }}
    )
    selection, error = selector.select(
        message="Prepare an ETH DCA setup for daily entries.",
        candidate_contracts=(FinnV2OperationRegistry().get("create_setup"),), facts={}, verified_context=None,
    )

    assert error is None
    assert selection is not None
    assert selection.entities["setup_type"] == "dca"
    assert selection.entities["concept"] == ""


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


def test_selector_exposes_safe_degraded_lineage_to_the_provider_contract():
    captured = {}

    def provider(**kwargs):
        captured.update(kwargs)
        return {"parsed": {
            "operation_id": "reformulate_previous_response", "confidence": 0.9,
            "entities": {}, "target_asset": None,
            "conversation_reference": "previous_verified_response",
            "missing_inputs": [], "ambiguity_reason": None,
        }}

    selection, error = FinnV2StructuredOperationSelectorService(provider=provider).select(
        message="Leg dat eenvoudiger uit.",
        candidate_contracts=(FinnV2OperationRegistry().get("reformulate_previous_response"),),
        facts={}, verified_context={"last_degraded_context": {"run_id": "run-1", "evidence_refs": ["E1"]}},
    )

    assert error is None and selection is not None
    assert "last_degraded_context" in captured["prompt"]
    assert "safe reformulation" in captured["system_role"]


def test_selector_manifest_keeps_capability_and_concrete_bot_reads_distinct():
    captured = {}

    def provider(**kwargs):
        captured.update(kwargs)
        return {"parsed": {
            "operation_id": "capability", "confidence": 0.9, "entities": {},
            "target_asset": None, "conversation_reference": "untrusted-reference",
            "missing_inputs": [], "ambiguity_reason": None,
        }}

    selection, error = FinnV2StructuredOperationSelectorService(provider=provider).select(
        message="Welke veilige hulp kan FINN in mijn plan bieden?",
        candidate_contracts=(
            FinnV2OperationRegistry().get("capability"),
            FinnV2OperationRegistry().get("read_active_plan"),
            FinnV2OperationRegistry().get("read_linked_bot"),
            FinnV2OperationRegistry().get("evaluate_bot"),
        ),
        facts={"discourse_act": "capability"},
        verified_context={"last_verified_context": {"verified_response_id": "prior"}},
    )

    assert error is None and selection is not None
    assert selection.conversation_reference is None
    assert "capability discourse" in captured["system_role"]
    assert "concrete bot question" in captured["system_role"]
    assert "last_safe_terminal_context" in captured["system_role"]
