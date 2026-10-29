"""The chat action must target the named indicator on the named market."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry
from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_operation_resolver_service import FinnV2OperationResolverService
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection
from backend.services.finn_v2_tool_adapters.indicator_tool_adapter import IndicatorToolAdapter
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService


REQUEST = "Wijzig alleen de weging van Volume voor BTC/EUR naar laag; laat BTC/USDT ongemoeid."


def test_named_pair_weight_change_is_a_complete_indicator_action():
    result = FinnV2OperationClassificationService().classify(message=REQUEST)
    assert result.operation_id == "update_indicator_configuration"
    assert result.selected_missing_inputs == ()
    assert result.supplied_inputs == {
        "asset": "BTC", "quote_currency": "EUR", "indicator": "volume",
        "category": "market", "changed_fields": {"weight": 0.6},
    }
    proposal = FinnV2ReasoningFallbackService._proposal_changes(
        operation_id=result.operation_id,
        supplied_inputs=dict(result.supplied_inputs), evidence_by_tool={},
    )
    assert proposal["after"]["quote_currency"] == "EUR"
    assert proposal["after"]["weight"] == 0.6


def test_two_positive_pairs_need_clarification_instead_of_guessing_a_market():
    contract = FinnV2OperationRegistry().get("update_indicator_configuration")
    state = FinnV2OperationStateService().resolve(
        contract=contract,
        message="Wijzig de Volume-weging voor BTC/EUR en BTC/USDT naar laag.",
        explicit_asset="BTC", conversation_context={},
    )
    assert "quote_currency" not in state.collected_inputs
    assert state.next_missing_input == "quote_currency"


def test_pair_clarification_accepts_explicit_quote_reply():
    contract = FinnV2OperationRegistry().get("update_indicator_configuration")
    service = FinnV2OperationStateService()
    first = service.resolve(
        contract=contract,
        message="Wijzig de Volume-weging voor BTC naar laag.",
        explicit_asset="BTC", conversation_context={},
    )
    assert first.next_missing_input == "quote_currency"
    continued = service.resolve(
        contract=contract, message="EUR", explicit_asset="BTC",
        conversation_context={"operation_state": first.dict()},
    )
    assert continued.collected_inputs["quote_currency"] == "EUR"
    assert continued.missing_required_inputs == []


def test_typed_indicator_mutation_cannot_become_a_different_write():
    registry = FinnV2OperationRegistry()
    for polarity, wrong, expected in (
        ("update", "watchlist_add", "update_indicator_configuration"),
        ("delete", "delete_setup", "delete_indicator_configuration"),
    ):
        selected = FinnV2StructuredOperationSelection(
            operation_id=wrong, confidence=0.9, entities={}, target_asset="BTC",
            conversation_reference=None, missing_inputs=(), ambiguity_reason=None,
        )
        resolved = FinnV2OperationResolverService(registry).resolve(
            selection=selected, candidates=registry.list(), conversation_context={},
            request_facts={"discourse_act": "operation_request", "action_polarity": polarity,
                           "primary_entity": "indicator_configuration",
                           "explicit_entities": ["indicator_configuration"]},
        )
        assert resolved.operation_id == expected


def test_confirmed_pair_weight_edit_preserves_mode_and_targets_only_eur(monkeypatch):
    registry = FinnV2ActionAdapterRegistry(SimpleNamespace())
    registry.flags.execute_indicator_changes_enabled = lambda: True
    eur = SimpleNamespace(id=41, asset_symbol="BTC", quote_currency="EUR")
    registry._exact_indicator_market = AsyncMock(return_value=eur)
    registry.pair_indicators.get = AsyncMock(return_value={
        "score_mode": "custom", "weight": 1.0,
        "rules": [{"score": value} for value in (10, 30, 50, 70, 90)],
    })
    registry.pair_indicators.save = AsyncMock()
    queued = []
    monkeypatch.setattr(
        "backend.services.finn_v2_action_adapter_registry.queue_indicator_score_refresh",
        lambda *args, **kwargs: queued.append((args, kwargs)),
    )

    result = asyncio.run(registry._update_indicator_configuration(7, {
        "target": {"asset": "BTC"},
        "change": {"indicator_id": "volume", "after": {
            "category": "market", "indicator_id": "volume",
            "quote_currency": "EUR", "weight": 0.6,
        }},
    }))

    assert result["pair"] == "BTC/EUR"
    registry._exact_indicator_market.assert_awaited_once_with("BTC", "EUR")
    saved = registry.pair_indicators.save.await_args
    assert saved.args[:4] == (7, eur, "market", "volume")
    assert saved.kwargs["mode"] == "edit"
    assert saved.kwargs["score_mode"] == "custom"
    assert saved.kwargs["weight"] == 0.6
    assert queued == [((7, "BTC"), {"market_id": 41})]


def test_pair_weight_is_available_to_finn_when_read_back():
    row = SimpleNamespace(
        indicator="volume", category="market", priority=60, enabled=True,
        symbol="BTC", asset_class="crypto", id=9, provenance="user_indicator_configs",
        config_json={"weight": 0.6},
    )
    item = IndicatorToolAdapter._serialize([row])[0].dict()
    facts = FinnV2ReasoningContextService._sanitize_facts(
        None,
        {"data": {"symbol": "BTC", "market_id": 41, "pair": "BTC/EUR",
                  "market": [item], "technical": [], "macro": []}},
        "read_indicator_configuration",
    )
    assert facts["pair"] == "BTC/EUR"
    assert facts["market"][0]["weight"] == 0.6
    assert facts["configured_indicators"][0]["weight"] == 0.6
