import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.services.finn_v2_responses_loop import FinnResponsesError, FinnResponsesLoop
from backend.services.finn_v2_responses_tool_catalog import (
    FinnResponsesToolCatalog,
    FinnResponsesToolError,
)
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.domain.finn_v2_runtime_contract import RuntimeContractConflictError
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService


def test_unavailable_market_evidence_keeps_typed_source_limitation():
    evidence = (
        {"scope": "read_active_asset", "status": "completed"},
        {"scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable"},
    )
    assert FinnResponsesAnswerVerifier._typed_failure_reason(evidence) == "source_unavailable"


def test_typed_fallback_uses_language_of_current_question():
    copy = FinnResponsesAnswerVerifier._fallback_copy
    assert copy("setup_ambiguous", message="Explain what my plan can safely conclude.").startswith("I found")
    assert copy("setup_ambiguous", message="Erkläre mir meinen gesamten Handelsplan.").startswith("Ich sehe")
    assert copy("previous_source_unavailable", message="Why?").startswith("I can't")
    assert copy("previous_source_unavailable", message="Warum?").startswith("Ich kann")


def test_guided_strategy_tool_is_limited_to_pending_registry_operation():
    catalog = FinnResponsesToolCatalog()
    definitions = catalog.definitions(guided_operation_id="create_strategy")
    assert [item["name"] for item in definitions] == ["create_or_update_trade_plan_proposal"]
    variants = definitions[0]["parameters"]["properties"]["payload"]
    assert variants["properties"]["operation_id"]["enum"] == ["create_strategy"]
    assert "base_amount" in variants["properties"]["inputs"]["properties"]
    assert "changed_fields" not in variants["properties"]["inputs"]["properties"]


def test_target_reselection_uses_only_registry_contracts_for_resolved_domain():
    definitions = FinnResponsesToolCatalog().definitions(retry_target_domain="strategy")
    assert all(item["name"].endswith("_proposal") for item in definitions)
    for item in definitions:
        payload = item["parameters"]["properties"]["payload"]
        variants = payload.get("oneOf", [payload])
        assert all(
            FinnV2OperationRegistry().require_supported(variant["properties"]["operation_id"]["enum"][0]).domain == "strategy"
            for variant in variants
        )
    assert any(item["name"] == "create_or_update_trade_plan_proposal" for item in definitions)


@pytest.mark.parametrize("model_value,expected", [
    ("vast", "fixed"), ("fixed", "fixed"), ("aangepast", "custom"),
    ("fest", "fixed"),
])
def test_model_strategy_execution_mode_uses_guided_contract_canonicalization(model_value, expected):
    assert FinnV2OperationStateService._canonical_input("execution_mode", model_value) == expected


@pytest.mark.parametrize("field,value,expected", [
    ("dca_frequency", "wekelijks", "weekly"),
    ("dca_frequency", "monthly", "monthly"),
    ("dca_day", "maandag", "monday"),
    ("dca_frequency", "soms", None),
])
def test_model_dca_inputs_share_guided_canonicalization(field, value, expected):
    assert FinnV2OperationStateService._canonical_input(field, value) == expected


def test_catalog_uses_registry_for_required_and_conditional_inputs():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    assert call.missing_inputs == ("timeframe", "name", "dca_frequency")
    assert call.operation_id == "create_setup"
    assert len(catalog.definitions()) == 15
    proposal = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    assert proposal["parameters"]["properties"]["payload"]["properties"]["inputs"]["properties"]["min_investment"]["type"] == "number"


def test_clarification_tool_accepts_one_natural_question_not_internal_fields():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("ask_for_clarification", {
        "question": "Welke van je twee BTC-setups bedoel je?", "reason": "choice_required",
    }).inputs["reason"] == "choice_required"
    with pytest.raises(FinnResponsesToolError, match="clarification_question_invalid"):
        catalog.validate("ask_for_clarification", {
            "question": "Wat is je setup_id?", "reason": "choice_required",
        })


def test_read_timeframe_cannot_be_a_selected_object_name():
    catalog = FinnResponsesToolCatalog()
    definition = next(item for item in catalog.definitions() if item["name"] == "get_active_plan_and_strategy")
    assert "setup_name" in definition["parameters"]["properties"]
    assert catalog.validate("get_active_plan_and_strategy", {
        "setup_name": "Matrix Strategy Parent",
    }).inputs["setup_name"] == "Matrix Strategy Parent"
    with pytest.raises(FinnResponsesToolError, match="read_timeframe_invalid"):
        catalog.validate("get_active_plan_and_strategy", {
            "asset": "BTC", "timeframe": "Matrix Strategy Parent",
        })
    assert catalog.validate("get_active_plan_and_strategy", {
        "asset": "BTC", "timeframe": "4h",
    }).inputs["timeframe"] == "4H"


def test_indicator_model_category_is_canonicalized_by_existing_catalog():
    contract = FinnV2OperationRegistry().require_supported("create_indicator_configuration")
    state = FinnV2OperationStateService().resolve(
        contract=contract,
        message="Maak een technische RSI-indicatorconfiguratie voor ADA.",
        explicit_asset=None,
        conversation_context={},
        supplied_inputs={"asset": "ADA", "indicator": "RSI", "category": "technisch"},
        model_tool_inputs=True,
    )
    assert state.collected_inputs["indicator"] == "rsi"
    assert state.collected_inputs["category"] == "technical"
    assert not state.missing_required_inputs


def test_model_changed_fields_use_canonical_setup_timeframe():
    assert FinnV2OperationStateService._canonical_input(
        "changed_fields", {"timeframe": "1 uur"}
    ) == {"timeframe": "1H"}


def test_catalog_rejects_model_owned_identity_and_undeclared_inputs():
    catalog = FinnResponsesToolCatalog()
    for inputs in ({"user_id": 3}, {"proposal_id": "other"}, {"bogus": True}):
        with pytest.raises(FinnResponsesToolError):
            catalog.validate(
                "create_dca_plan_proposal",
                {"operation_id": "create_setup", "inputs": inputs},
            )
    with pytest.raises(FinnResponsesToolError):
        catalog.validate("confirm_proposal", {})
    echoed_entity = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "update_setup", "inputs": {"setup_id": 99, "changed_fields": {"timeframe": "1H"}}},
    )
    assert echoed_entity.inputs == {"changed_fields": {"timeframe": "1H"}}
    with pytest.raises(FinnResponsesToolError, match="proposal_input_type_invalid"):
        catalog.validate(
            "create_dca_plan_proposal",
            {"operation_id": "create_setup", "inputs": {"min_investment": "100"}},
        )
    nullable = catalog.validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"min_investment": None, "symbol": "BTC"}},
    )
    assert "min_investment" not in nullable.inputs
    assert "min_investment" not in nullable.required_inputs
    placeholders = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {
            "name": "New Strategy", "base_amount": 0, "entry": "", "targets": [],
        }},
    )
    assert placeholders.inputs == {"name": "New Strategy"}
    assert {"base_amount", "entry", "targets"}.issubset(placeholders.missing_inputs)
    strategy_tool = next(item for item in catalog.definitions() if item["name"] == "create_or_update_trade_plan_proposal")
    variants = strategy_tool["parameters"]["properties"]["payload"]["oneOf"]
    assert all("setup_id" not in variant["properties"]["inputs"]["properties"] for variant in variants)
    update_setup_schema = next(
        variant for variant in variants
        if variant["properties"]["operation_id"]["enum"] == ["update_setup"]
    )
    assert "draft_intent" in update_setup_schema["required"]
    assert set(update_setup_schema["properties"]["inputs"]["properties"]) == {"changed_fields"}
    assert "update_setup:" in strategy_tool["description"]
    assert "Target saved object types: setup, strategy" in strategy_tool["description"]
    assert "Model-supplied fields allowed for this operation: changed_fields" in strategy_tool["description"]
    assert "updating an existing saved object is draft_intent=new" in strategy_tool["description"]
    paper_tool = next(item for item in catalog.definitions() if item["name"] == "manage_paper_bot_proposal")
    assert "Target saved object types: bot" in paper_tool["description"]
    assert all(
        "activate_bot" not in variant["properties"]["operation_id"]["enum"]
        for variant in paper_tool["parameters"]["properties"]["payload"]["oneOf"]
    )
    nested = catalog.validate("create_or_update_trade_plan_proposal", {
        "payload": {"operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}}},
    })
    assert nested.operation_id == "update_setup"


def test_responses_provider_call_disables_sdk_retries_and_sets_timeout():
    fake = FakeResponses(response("r1", text="Een algemene uitleg."))
    client = SimpleNamespace(with_options=Mock(return_value=SimpleNamespace(responses=fake)))

    async def execute(_call):
        raise AssertionError("no tool calls expected")

    asyncio.run(FinnResponsesLoop(client=client, executor=execute).run(
        message="Wat is RSI?", instructions="Use FINN contracts.",
    ))
    assert client.with_options.call_args.kwargs["max_retries"] == 0
    assert 0 < client.with_options.call_args.kwargs["timeout"] <= 12


def test_invalid_sibling_operation_field_returns_registry_driven_repair_hint():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"name": "Existing Setup"},
        }),)),
        response("r2", text="Ik kan de setup pas wijzigen na een geldig voorstel."),
    )

    async def execute(_call):
        raise AssertionError("invalid tool arguments must not reach execution")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Wijzig Existing Setup", instructions="Use FINN contracts."
    ))
    rejected = result.tool_trace[0]["result"]
    contract = FinnV2OperationRegistry().require_supported("update_setup")
    assert rejected["reason"] == "proposal_input_not_in_action_contract"
    assert rejected["operation_id"] == "update_setup"
    assert rejected["allowed_inputs"] == [field for field in contract.input_fields if field != "setup_id"]
    assert rejected["required_inputs"] == list(contract.required_inputs)


def test_dca_frequency_tool_enum_is_from_the_existing_action_contract():
    registry = FinnV2OperationRegistry()
    contract = registry.require_supported("create_setup")
    catalog = FinnResponsesToolCatalog(registry=registry)
    tool = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    payload = tool["parameters"]["properties"]["payload"]
    variant = payload["oneOf"][0] if "oneOf" in payload else payload
    frequency = variant["properties"]["inputs"]["properties"]["dca_frequency"]
    assert frequency["enum"] == list(contract.allowed_values_for("dca_frequency"))
    with pytest.raises(FinnResponsesToolError, match="proposal_input_value_invalid:dca_frequency"):
        catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "draft_intent": "new", "inputs": {
                "setup_type": "dca", "dca_frequency": "wekelijk",
            },
        })


def test_invalid_proposal_is_retried_once_with_the_same_registry_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"name": "Existing Setup"},
        }),)),
        response("r2", calls=(tool_call("c2", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}},
        }),)),
        response("r3", text="Ik heb het wijzigingsvoorstel voorbereid."),
    )

    async def execute(_call):
        return {"status": "validation_pending", "confirmation_required": True}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wijzig mijn setup", instructions="Gebruik het contract"))
    assert result.tool_trace[0]["result"]["reason"] == "proposal_input_not_in_action_contract"
    assert fake.requests[1]["tool_choice"] == {
        "type": "function", "name": "create_or_update_trade_plan_proposal",
    }
    assert fake.requests[2]["tool_choice"] == "none"


def test_read_then_invalid_update_can_repair_with_the_registry_tool():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {}),)),
        response("r2", calls=(tool_call("c2", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"timeframe": "1H"},
        }),)),
        response("r3", calls=(tool_call("c3", "create_or_update_trade_plan_proposal", {
            "operation_id": "update_setup", "inputs": {"changed_fields": {"timeframe": "1H"}},
        }),)),
        response("r4", text="Ik heb het wijzigingsvoorstel voorbereid."),
    )

    async def execute(call):
        if call.operation_id is None:
            return {"status": "completed", "results": []}
        return {"status": "validation_pending", "confirmation_required": True}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wijzig mijn setup", instructions="Gebruik het contract"))
    assert len(result.tool_trace) == 3
    assert result.tool_trace[1]["result"]["reason"] == "proposal_input_not_in_action_contract"
    assert fake.requests[2]["tool_choice"] == {
        "type": "function", "name": "create_or_update_trade_plan_proposal",
    }
    assert fake.requests[3]["tool_choice"] == "none"


def test_catalog_rejects_non_scalar_read_selectors():
    catalog = FinnResponsesToolCatalog()
    for arguments in ({"asset": {"symbol": "BTC"}}, {"timeframe": ["4H"]}):
        with pytest.raises(FinnResponsesToolError, match="read_arguments_invalid"):
            catalog.validate("get_market_snapshot", arguments)
    assert catalog.validate(
        "get_active_plan_and_strategy", {"asset": " BTC ", "timeframe": ""},
    ).inputs == {"asset": "BTC"}


def test_proposal_candidate_uses_registry_contract_and_existing_guided_state():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een BTC DCA-setup", conversation_context={}, verified_asset="BTC",
    )
    plan = analysis.request_plan
    assert plan.operation_id == "create_setup"
    assert plan.selector_source == "responses_tool_call"
    assert plan.operation_state["collected_inputs"]["symbol"] == "BTC"
    assert plan.missing_information == ["timeframe", "name", "dca_frequency"]


def test_explicit_setup_name_overrides_truncated_model_candidate():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {
            "setup_type": "dca", "symbol": "BTC", "timeframe": "4H",
            "name": "Responses Build DCA", "dca_frequency": "weekly",
            "min_investment": 150,
        }},
    )
    result = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak een BTC DCA setup op 4H met de naam Responses Build DCA 2eb7de2e, 150 euro per week.",
        conversation_context={}, verified_asset="BTC",
    )
    assert result.request_plan.operation_state["collected_inputs"]["name"] == "Responses Build DCA 2eb7de2e"


@pytest.mark.parametrize("model_timeframe", ["1W", "wekelijks"])
def test_weekly_dca_cadence_cannot_satisfy_setup_chart_timeframe(model_timeframe):
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {
            "setup_type": "dca", "symbol": "BTC", "name": "Build Smoke BTC",
            "dca_frequency": "weekly", "timeframe": model_timeframe,
        }},
    )
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=call, message="Maak een wekelijkse BTC DCA-setup met naam Build Smoke BTC",
        conversation_context={}, verified_asset="BTC",
    )
    state = first.request_plan.operation_state
    assert "timeframe" not in state["collected_inputs"]
    assert "timeframe" in state["missing_required_inputs"]


def test_saved_indicator_configuration_does_not_bundle_unavailable_current_values():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("get_indicator_snapshot", {}).read_tools == ("read_indicator_configuration",)
    assert catalog.validate("get_current_technical_snapshot", {}).read_tools == ("read_technical_snapshot",)


def test_indicator_read_options_come_from_existing_macro_catalog():
    evidence = FinnResponsesReadExecutor._macro_catalog_evidence()
    assert evidence["scope"] == "available_macro_indicator_catalog"
    assert evidence["source"] == "macro_indicator_catalog"
    assert any(item["name"] == "dxy" for item in evidence["data"]["supported_options"])
    assert evidence["data"]["proposal_operation_id"] == "create_indicator_configuration"


def test_proposal_candidate_rejects_cross_asset_context():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"}},
    )
    with pytest.raises(ValueError, match="proposal_asset_conflicts"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak een BTC DCA-setup", conversation_context={}, verified_asset="AAPL",
        )


def test_proposal_candidate_does_not_trust_an_unmentioned_model_asset():
    call = FinnResponsesToolCatalog().validate(
        "create_dca_plan_proposal",
        {"operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "AEX"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een DCA-setup", conversation_context={}, verified_asset=None,
    )
    assert analysis.request_plan.operation_state["collected_inputs"].get("symbol") != "AEX"
    with pytest.raises(ValueError, match="proposal_asset_ambiguous"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak een BTC en ETH setup", conversation_context={}, verified_asset=None,
        )


def test_saved_object_update_is_not_treated_as_draft_revision():
    call = FinnResponsesToolCatalog().validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "update_setup", "draft_intent": "revise", "inputs": {
            "setup_id": 99, "changed_fields": {"timeframe": "1H"},
        }},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Wijzig mijn bestaande setup naar 1H",
        conversation_context={},
        verified_asset=None,
    )
    assert analysis.request_plan.operation_id == "update_setup"
    assert analysis.request_plan.operation_state["collected_inputs"] == {"changed_fields": {"timeframe": "1H"}}
    assert "setup_id" in analysis.request_plan.missing_information


def test_parent_read_name_does_not_become_new_strategy_name():
    call = FinnResponsesToolCatalog().validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {"name": "Parent Setup"}},
    )
    analysis = FinnResponsesProposalSelection().from_call(
        call=call,
        message="Maak een strategie voor Parent Setup.",
        conversation_context={},
        verified_asset=None,
        read_context=[{"results": [{"data": {"name": "Parent Setup"}}]}],
    )
    assert "name" not in analysis.request_plan.operation_state["collected_inputs"]
    assert "name" in analysis.request_plan.missing_information


def test_parent_name_without_explicit_new_name_is_not_supplied_even_without_read():
    catalog = FinnResponsesToolCatalog()
    call = catalog.validate(
        "create_or_update_trade_plan_proposal",
        {"operation_id": "create_strategy", "inputs": {"name": "Parent Setup"}},
    )
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=call, message="Maak een strategie voor Parent Setup.",
        conversation_context={}, verified_asset=None,
    )
    assert "name" in first.request_plan.missing_information
    named = selection.from_call(
        call=call, message="Maak een strategie met de naam Parent Setup voor mijn plan.",
        conversation_context={}, verified_asset=None,
    )
    assert named.request_plan.operation_state["collected_inputs"]["name"] == "Parent Setup"


def test_revised_dca_draft_retains_prior_fields_and_changes_only_amount():
    catalog = FinnResponsesToolCatalog()
    contract = catalog.registry.require_supported("create_setup")
    prior_state = {
        "operation_id": "create_setup", "contract_version": contract.version,
        "status": "proposed", "open_proposal_id": "proposal-owned-by-conversation",
        "collected_inputs": {
            "setup_type": "dca", "symbol": "BTC", "timeframe": "4H",
            "name": "Responses Revised 0923", "dca_frequency": "wekelijks",
            "dca_day": "maandag", "min_investment": 150,
        },
        "missing_required_inputs": [],
    }
    context = {"proposal_revision": {
        "proposal_id": "proposal-owned-by-conversation",
        "operation_id": "create_setup", "guided_state": prior_state,
    }}
    call = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "revise",
        "inputs": {"min_investment": 100},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC",
    )
    state = analysis.request_plan.operation_state
    assert state["open_proposal_id"] == "proposal-owned-by-conversation"
    assert state["collected_inputs"]["name"] == "Responses Revised 0923"
    assert state["collected_inputs"]["min_investment"] == 100
    assert state["missing_required_inputs"] == []
    omitted_intent = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "inputs": {"min_investment": 100},
    })
    implicit_revision = FinnResponsesProposalSelection().from_call(
        call=omitted_intent, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC",
    ).request_plan.operation_state
    assert implicit_revision["open_proposal_id"] == "proposal-owned-by-conversation"
    assert implicit_revision["collected_inputs"]["name"] == "Responses Revised 0923"
    assert implicit_revision["missing_required_inputs"] == []
    explicitly_new = catalog.validate("create_dca_plan_proposal", {
        "operation_id": "create_setup", "draft_intent": "new",
        "inputs": {"setup_type": "dca", "min_investment": 100},
    })
    new_state = FinnResponsesProposalSelection().from_call(
        call=explicitly_new, message="Maak een nieuwe DCA setup.",
        conversation_context=context, verified_asset="BTC",
    ).request_plan.operation_state
    assert new_state["open_proposal_id"] is None
    assert new_state["collected_inputs"].get("name") != "Responses Revised 0923"
    with pytest.raises(ValueError, match="revisable_proposal_not_found"):
        FinnResponsesProposalSelection().from_call(
            call=call, message="Maak er 100 euro per week van.",
            conversation_context={}, verified_asset="BTC",
        )


def test_model_tool_call_fills_only_pending_guided_slot():
    catalog = FinnResponsesToolCatalog()
    selection = FinnResponsesProposalSelection()
    first = selection.from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"setup_type": "dca", "symbol": "BTC", "timeframe": "4H"},
        }),
        message="Maak een BTC DCA-setup op 4H",
        conversation_context={},
        verified_asset="BTC",
    )
    context = {"active_guided_operation": first.request_plan.operation_state}
    assert first.request_plan.operation_state["next_missing_input"] == "name"
    second = selection.from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"name": "FINN DCA Flow 0914", "timeframe": "1D"},
        }),
        message="FINN DCA Flow 0914",
        conversation_context=context,
        verified_asset="BTC",
    )
    state = second.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "FINN DCA Flow 0914"
    assert state["collected_inputs"]["timeframe"] == "4H"
    assert state["next_missing_input"] == "dca_frequency"


def test_model_generated_name_is_not_user_supplied_input():
    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "operation_id": "create_setup",
        "inputs": {"symbol": "BTC", "timeframe": "4H", "setup_type": "dca", "name": "DCA BTC 4H"},
    })
    first = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een nieuwe DCA-setup voor BTC op 4H.",
        conversation_context={}, verified_asset="BTC",
    )
    assert "name" not in first.request_plan.operation_state["collected_inputs"]
    assert first.request_plan.operation_state["next_missing_input"] == "name"
    second = FinnResponsesProposalSelection().from_call(
        call=FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"name": "DCA BTC 4H", "dca_frequency": "weekly"},
        }),
        message="Responses Guided 0914",
        conversation_context={"active_guided_operation": first.request_plan.operation_state},
        verified_asset="BTC",
    )
    state = second.request_plan.operation_state
    assert state["collected_inputs"]["name"] == "Responses Guided 0914"
    assert "dca_frequency" not in state["collected_inputs"]


def test_pending_guided_operation_is_persisted_without_model_skipping_it():
    catalog = FinnResponsesToolCatalog()
    first = FinnResponsesProposalSelection().from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),
        message="Maak een DCA-setup voor BTC", conversation_context={}, verified_asset="BTC",
    )
    front = object.__new__(FinnResponsesFrontDoor)
    fake = FakeResponses(response("r1", text="Ik ga verder."))
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-guided"
    front.proposals = FinnResponsesProposalSelection()
    context = {"active_guided_operation": first.request_plan.operation_state}
    result = asyncio.run(front.run(
        message="4H", instructions="Vul het gevraagde veld", conversation_context=context,
        verified_asset="BTC",
    ))
    assert not fake.requests
    assert result.proposal_analysis.request_plan.operation_id == "create_setup"
    assert result.proposal_analysis.request_plan.operation_state["collected_inputs"]["timeframe"] == "4H"


class FakeResponses:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def response(response_id, *, text="", calls=()):
    return SimpleNamespace(id=response_id, status="completed", output_text=text, output=list(calls))


def tool_call(call_id, name, arguments):
    return SimpleNamespace(type="function_call", call_id=call_id, name=name, arguments=json.dumps(arguments))


def test_tool_relevance_guard_uses_typed_responses_without_exposing_identity():
    fake = FakeResponses(response("judge", text='{"requests_change": false}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    aligned = asyncio.run(guard.is_relevant(
        message="Past wekelijkse BTC-DCA bij mijn plan?", previous_answer="",
        tool_name="create_dca_plan_proposal", tool_purpose="Maak een DCA-setup",
        is_proposal=True,
    ))
    assert aligned is False
    request = fake.requests[0]
    assert request["tool_choice"] == "none" and request["store"] is False
    assert request["text"]["format"]["type"] == "json_schema"
    assert "user_id" not in request["input"] and "proposal_id" not in request["input"]


def test_previous_answer_sufficiency_is_model_judgment_not_keyword_route():
    fake = FakeResponses(response("judge", text='{"kind": "explain_previous"}'))
    guard = FinnResponsesToolRelevanceGuard(SimpleNamespace(responses=fake))
    assert asyncio.run(guard.previous_answer_suffices(
        message="Waarom?",
        previous_answer="De opgeslagen strategie is niet op actuele markt- en risicodata beoordeeld.",
    )) is True
    assert fake.requests[0]["tool_choice"] == "none"


@pytest.mark.parametrize("answer", [
    "Setup ID: 7855", "Strategy-ID: 12", "finn-v2-run-123abc",
])
def test_coach_answer_rejects_internal_identifiers(answer):
    assert FinnResponsesAnswerVerifier._contains_internal_identifier(answer)
    assert not FinnResponsesAnswerVerifier._contains_internal_identifier(
        "Je setup BTC 4H heeft een opgeslagen stop-loss van 90."
    )


def test_catalog_focus_audit_rejects_many_options_for_one_choice():
    fake = FakeResponses(response("judge", text=json.dumps({
        "focused": False, "selected_option": "DXY",
        "replacement": "Overweeg DXY als aanvulling; het toont de algemene dollarsterkte.",
    })))
    verifier = FinnResponsesAnswerVerifier(client=SimpleNamespace(responses=fake))
    focused, replacement = asyncio.run(verifier._catalog_answer_is_focused(
        question="Welk macro-indicator mis ik nog en waarom?",
        answer="Overweeg DXY, VIX en CPI.",
        options=[
            {"name": "DXY", "display_name": "US Dollar Index (Derived Basket)"},
            {"name": "VIX", "display_name": "CBOE Volatility Index"},
            {"name": "CPI", "display_name": "Consumer Price Index"},
        ], remaining=None,
    ))
    assert focused is False
    assert "DXY" in replacement and "VIX" not in replacement
    assert fake.requests[0]["store"] is False
    assert fake.requests[0]["text"]["format"]["type"] == "json_schema"


@pytest.mark.parametrize("sufficiency", [True, None])
def test_sufficient_or_undecided_previous_answer_limits_short_followup_to_direct_answer(sufficiency):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "answer_directly", {"uses_previous_response": True}),)),
        response("r2", text="Een actuele markt- en risicobeoordeling ontbreekt nog."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-why"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value=sufficiency),
        is_relevant=AsyncMock(),
    )
    called = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            called.append(call.name)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Waarom?", instructions="Gebruik de vorige geverifieerde uitleg",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "Deze strategie heeft nog geen actuele markt- en risicobeoordeling."},
    ))
    assert called == ["answer_directly"]
    assert [tool["name"] for tool in fake.requests[0]["tools"]] == ["answer_directly"]
    assert "No new market facts" in fake.requests[0]["instructions"]
    assert fake.requests[1]["tool_choice"] == "none"
    assert result.proposal_analysis is None


def test_guided_strategy_slot_binds_without_provider_call():
    fake = FakeResponses()
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-guided-stop"
    front.proposals = FinnResponsesProposalSelection()
    contract = front.proposals.registry.require_supported("create_strategy")
    initial = front.proposals.states.resolve(
        contract=contract, message="", explicit_asset="BTC", conversation_context={},
        supplied_inputs={
            "setup_id": 42, "name": "BTC Plan", "execution_mode": "fixed",
            "base_amount": 100, "entry": "76000",
        },
    )
    assert initial.next_missing_input == "stop_loss"
    result = asyncio.run(front.run(
        message="Stop-loss op 72000", instructions="unused",
        conversation_context={"active_guided_operation": initial.dict()},
        verified_asset="BTC", previous_response_id="resp_previous",
    ))
    state = result.proposal_analysis.request_plan.operation_state
    assert not fake.requests
    assert result.proposal_analysis.request_plan.operation_id == "create_strategy"
    assert state["collected_inputs"]["base_amount"] == 100
    assert state["collected_inputs"]["entry"] == "76000"
    assert state["collected_inputs"]["stop_loss"] == 72000.0


def test_irrelevant_proposal_is_retried_without_creating_draft():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {}),)),
        response("r3", text="Ik heb eerst je opgeslagen plan nodig om dit te beoordelen."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-fit"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(is_relevant=AsyncMock(return_value=False))

    async def read(_call):
        return {"status": "partial", "results": []}

    class Reads:
        session_factory = None

        async def __call__(self, call):
            return await read(call)

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Past een wekelijkse BTC-DCA bij mijn plan?", instructions="Beoordeel het plan",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis is None
    assert result.response.tool_trace[0]["status"] == "retry"
    front.relevance_guard.is_relevant.assert_awaited()
    assert front.relevance_guard.is_relevant.await_args.kwargs["tool_name"] == "create_setup"


def test_irrelevant_followup_read_is_retried_before_data_access():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_current_technical_snapshot", {}),)),
        response("r2", calls=(tool_call("c2", "answer_directly", {"uses_previous_response": True}),)),
        response("r3", text="Omdat de actuele beoordeling nog niet is uitgevoerd."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-followup"
    front.proposals = FinnResponsesProposalSelection()
    front.relevance_guard = SimpleNamespace(
        previous_answer_suffices=AsyncMock(return_value=False),
        is_relevant=AsyncMock(return_value=False),
    )
    read_calls = []

    class Reads:
        session_factory = None

        async def __call__(self, call):
            read_calls.append(call.name)
            return {"status": "completed", "results": []}

    front.reads = Reads()
    result = asyncio.run(front.run(
        message="Waarom?", instructions="Verklaar het vorige antwoord",
        conversation_context={}, verified_asset="BTC",
        previous_response={"answer": "Een actuele markt- en risicobeoordeling ontbreekt nog."},
    ))
    assert read_calls == ["answer_directly"]
    assert result.response.tool_trace[0]["status"] == "retry"


def test_clarification_tool_stops_at_one_choice_and_returns_typed_terminal_question():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        response("r2", calls=(tool_call("c2", "ask_for_clarification", {
            "question": "Welke risicostijl past bij jou?", "reason": "choice_required",
        }),)),
        response("r3", text="Welke risicostijl past bij jou?"),
    )

    async def execute(call):
        if call.name == "ask_for_clarification":
            return {"status": "needs_input", **call.inputs}
        return {"status": "partial", "results": [{
            "scope": "read_profile", "status": "completed", "data": {"has_profile": False},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Beoordeel mijn BTC-plan", instructions="Gebruik FINN-tools"))
    assert fake.requests[2]["tool_choice"] == "none"
    answer = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message="Beoordeel mijn BTC-plan", result=result,
    ))
    assert answer.status == "clarification_required"
    assert answer.clarification == {
        "question": "Welke risicostijl past bij jou?", "reason": "choice_required",
    }


def test_recovery_clarification_reuses_completed_read_from_same_run():
    fake = FakeResponses(
        response("r2", calls=(tool_call("c2", "ask_for_clarification", {
            "question": "Wat is je risicostijl?", "reason": "user_detail_required",
        }),)),
        response("r3", text="Wat is je risicostijl?"),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.reads = SimpleNamespace(session_factory=None)
    front.user_id = 21
    front.run_id = "run-recovery"
    result = asyncio.run(front.run(
        message="Maak een plan voor mij", instructions="Vraag gericht door",
        conversation_context={}, verified_asset="BTC",
        prior_tool_trace=({"name": "get_my_profile_and_risk_style", "status": "completed"},),
    ))
    assert result.response.tool_trace[0]["result"]["status"] == "needs_input"


def test_resumed_choice_allows_one_read_round_then_only_answer_or_question():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "setup_name": "Matrix Strategy Update Parent",
        }),)),
        response("r2", text="Deze strategy gebruikt je gekozen setup."),
    )

    async def execute(_call):
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed",
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Matrix Strategy Update Parent", instructions="Gebruik FINN-tools",
          resuming_clarification=True))
    assert result.text
    assert {item["name"] for item in fake.requests[1]["tools"]} == {
        "ask_for_clarification", "answer_directly",
    }


def test_new_topic_after_clarification_keeps_normal_read_tools():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_market_snapshot", {"asset": "AAPL"}),)),
        response("r2", text="Ik heb nog geen actuele AAPL-snapshot."),
    )

    async def execute(_call):
        return {"status": "partial", "results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat is de actuele AAPL-koers?", instructions="Gebruik FINN-tools",
          resuming_clarification=True))
    assert "get_indicator_snapshot" in {item["name"] for item in fake.requests[1]["tools"]}


def test_unavailable_market_data_is_not_a_user_choice():
    result = FinnResponsesResult("Ik heb geen actuele koers en kan dit nog niet beoordelen.", "r1", ({
        "name": "get_market_snapshot", "status": "partial",
        "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable",
        }]},
    },))
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat is de actuele BTC-koers?", result=result,
    ))
    assert answer.status == "completed"
    assert answer.clarification is None


def test_responses_loop_handles_multiple_calls_then_answer():
    fake = FakeResponses(
        response("r1", calls=(
            tool_call("c1", "get_my_profile_and_risk_style", {}),
            tool_call("c2", "get_active_asset_context", {"asset": "AAPL"}),
        )),
        response("r2", text="Je Apple-plan heeft nog geen koersbewijs."),
    )
    outputs = []

    async def execute(call):
        outputs.append(call)
        return {"status": "completed", "asset": call.inputs.get("asset")}

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Wat betekent dit voor Apple?", instructions="Gebruik FINN-feiten."
    ))
    assert result.response_id == "r2"
    assert len(outputs) == 2
    assert [item["call_id"] for item in fake.requests[1]["input"]] == ["c1", "c2"]
    assert fake.requests[1]["previous_response_id"] == "r1"
    assert all(request["parallel_tool_calls"] is False for request in fake.requests)
    assert all(tool["name"] not in {"confirm_proposal", "execute_confirmed_proposal"} for tool in fake.requests[0]["tools"])


def test_conflicting_proposal_calls_create_no_draft_before_single_retry():
    fake = FakeResponses(
        response("r1", calls=(
            tool_call("c1", "create_or_update_trade_plan_proposal", {
                "payload": {"operation_id": "update_setup", "draft_intent": "revise",
                            "inputs": {"changed_fields": {"min_investment": 200}}},
            }),
            tool_call("c2", "create_or_update_trade_plan_proposal", {
                "payload": {"operation_id": "create_setup", "draft_intent": "new",
                            "inputs": {"name": "Separate DCA", "symbol": "BTC", "setup_type": "dca"}},
            }),
        )),
        response("r2", calls=(tool_call("c3", "create_or_update_trade_plan_proposal", {
            "payload": {"operation_id": "create_setup", "draft_intent": "new",
                        "inputs": {"name": "Separate DCA", "symbol": "BTC", "setup_type": "dca"}},
        }),)),
        response("r3", text="Ik heb een nieuw concept voorbereid."),
    )
    executed = []

    async def execute(call):
        executed.append(call.operation_id)
        return {"status": "needs_input", "missing_inputs": ["dca_frequency"]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Maak daarnaast een nieuwe setup", instructions="Gebruik FINN-contracten"))
    assert [item["result"]["reason"] for item in result.tool_trace[:2]] == [
        "multiple_action_proposals", "multiple_action_proposals",
    ]
    assert executed == ["create_setup"]
    assert fake.requests[1]["tool_choice"] == "required"
    assert all(request["parallel_tool_calls"] is False for request in fake.requests)


def test_dca_revision_does_not_turn_weekly_frequency_into_chart_timeframe():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "payload": {"operation_id": "create_setup", "draft_intent": "revise", "inputs": {
            "name": "BTC DCA", "symbol": "BTC", "timeframe": "4H", "setup_type": "dca",
            "dca_frequency": "weekly", "dca_day": "monday", "min_investment": 100,
        }},
    })
    context = {"proposal_revision": {
        "operation_id": "create_setup", "proposal_id": "owned-draft",
        "guided_state": {
            "operation_id": "create_setup", "status": "proposed",
            "contract_version": FinnV2OperationRegistry().require_supported("create_setup").version,
            "open_proposal_id": "owned-draft",
            "collected_inputs": {"name": "BTC DCA", "symbol": "BTC", "timeframe": "4H",
                                 "setup_type": "dca", "dca_frequency": "weekly",
                                 "dca_day": "monday", "min_investment": 150},
            "missing_required_inputs": [], "next_missing_input": None,
        },
    }}
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak er 100 euro per week van.",
        conversation_context=context, verified_asset="BTC", read_context=[],
    )
    assert analysis.request_plan.operation_state["collected_inputs"]["timeframe"] == "4H"


def test_new_dca_weekly_cadence_cannot_supply_missing_chart_timeframe():
    from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog

    call = FinnResponsesToolCatalog().validate("create_dca_plan_proposal", {
        "payload": {"operation_id": "create_setup", "draft_intent": "new", "inputs": {
            "name": "BTC DCA", "symbol": "BTC", "timeframe": "1W", "setup_type": "dca",
            "dca_frequency": "weekly", "min_investment": 100,
        }},
    })
    analysis = FinnResponsesProposalSelection().from_call(
        call=call, message="Maak een BTC DCA setup van 100 euro per week.",
        conversation_context={}, verified_asset="BTC", read_context=[],
    )
    assert "timeframe" in analysis.request_plan.operation_state["missing_required_inputs"]


def test_valid_proposal_call_is_followed_only_by_a_final_answer():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),)),
        response("r2", text="Ik heb een concept klaar; wat is de naam?"),
    )

    async def execute(_call):
        return {"status": "needs_input", "missing_inputs": ["name"]}

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Maak een DCA-setup", instructions="Use FINN contracts."
    ))
    assert result.response_id == "r2"
    assert fake.requests[1]["tool_choice"] == "none"
    assert fake.requests[0]["tool_choice"] == "required"


def test_provider_failure_has_no_legacy_fallback():
    fake = FakeResponses(RuntimeError("provider down"))

    async def execute(_call):
        raise AssertionError("not reached")

    with pytest.raises(FinnResponsesError, match="responses_provider_error"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Hallo", instructions="Help"
        ))
    assert len(fake.requests) == 1


def test_responses_loop_reads_typed_output_when_output_text_is_empty():
    typed_message = SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text="Je plan is nog niet compleet.")],
    )
    fake = FakeResponses(response("r1", calls=(typed_message,)))

    async def execute(_call):
        raise AssertionError("no tool was requested")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Is mijn plan compleet?", instructions="Gebruik FINN-feiten."
    ))
    assert result.text == "Je plan is nog niet compleet."
    assert result.tool_trace == ()


def test_model_cannot_call_confirmation_or_execution():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "execute_confirmed_proposal", {}),)),
        response("r2", text="Ik kan dit niet zonder je bevestiging uitvoeren."),
    )

    async def execute(_call):
        raise AssertionError("unauthorized model tool reached executor")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Voer uit", instructions="Safety"
    ))
    assert result.tool_trace[0]["status"] == "unavailable"


def test_read_executor_uses_server_owner_and_does_not_invent_as_of():
    class FakeReads:
        def __init__(self):
            self.calls = []

        async def execute_tool(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                success=True, availability="available", freshness_status="unknown",
                source="internal", asset="AAPL", result={"name": "Plan"}, error_codes=[],
            )

    executor = object.__new__(FinnResponsesReadExecutor)
    executor.user_id = 44
    executor.run_id = "run-1"
    executor.reads = FakeReads()
    call = FinnResponsesToolCatalog().validate("get_active_plan_and_strategy", {"asset": "AAPL"})
    result = asyncio.run(executor(call))
    assert len(result["results"]) == 2
    assert result["results"][0]["as_of"] is None
    assert "not a current market" in result["evidence_boundary"]
    assert all(kwargs["user_id"] == 44 and kwargs["run_id"] == "run-1" for kwargs in executor.reads.calls)


def test_read_executor_closes_each_database_session_before_provider_resumes(monkeypatch):
    opened = []

    class Session:
        async def __aenter__(self):
            opened.append(self)
            return self

        async def __aexit__(self, *_args):
            opened.remove(self)

    class ToolService:
        def __init__(self, session):
            assert session in opened

        async def execute_tool(self, **_kwargs):
            return SimpleNamespace(
                success=True, availability="available", freshness_status="fresh",
                source="owned_database", asset="BTC", result={"as_of": "2026-09-23T10:00:00Z"},
                error_codes=[],
            )

    monkeypatch.setattr(
        "backend.services.finn_v2_responses_read_executor.FinnV2ToolExecutionService", ToolService,
    )
    executor = FinnResponsesReadExecutor(session_factory=Session, user_id=44, run_id="run-1")
    call = FinnResponsesToolCatalog().validate("get_active_plan_and_strategy", {"asset": "BTC"})
    result = asyncio.run(executor(call))
    assert opened == []
    assert len(result["results"]) == 2
    assert all(item["as_of"] == "2026-09-23T10:00:00Z" for item in result["results"])


def test_responses_exchange_is_owner_bound_and_single_write():
    row = SimpleNamespace(user_id=7, run_id="run-7", conversation_id="conv-7", state_json={})
    repo = object.__new__(FinnV2RuntimeContractRepository)
    repo._required_for_update = AsyncMock(return_value=row)

    async def write_revision(*, row, state):
        row.state_json = state
        return row

    repo._write_revision = write_revision
    with pytest.raises(RuntimeContractConflictError, match="owner_mismatch"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=8, response_id="resp-7", tool_trace=[], answer="Antwoord",
        ))
    result = asyncio.run(repo.record_responses_exchange(
        run_id="run-7", user_id=7, response_id="resp-7",
        tool_trace=[{"call_id": "c1", "status": "completed"}], answer="Antwoord",
    ))
    assert result.state_json["responses_exchange"]["conversation_id"] == "conv-7"
    with pytest.raises(RuntimeContractConflictError, match="already_recorded"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=7, response_id="resp-8", tool_trace=[], answer="Anders",
        ))
    with pytest.raises(RuntimeContractConflictError, match="already_recorded"):
        asyncio.run(repo.record_responses_exchange(
            run_id="run-7", user_id=7, response_id="resp-8", tool_trace=[], answer="Anders",
            supersedes_response_id="wrong-response",
        ))
    recovered = asyncio.run(repo.record_responses_exchange(
        run_id="run-7", user_id=7, response_id="resp-8",
        tool_trace=[{"call_id": "c1"}, {"call_id": "c2"}], answer="Hersteld antwoord",
        supersedes_response_id="resp-7",
    ))
    assert recovered.state_json["responses_exchange"]["supersedes_response_id"] == "resp-7"
    assert [item["call_id"] for item in recovered.state_json["responses_exchange"]["tool_trace"]] == ["c1", "c2"]


def test_pending_clarification_is_persisted_on_the_owner_conversation_contract():
    row = SimpleNamespace(user_id=7, run_id="run-7", conversation_id="conv-7", state_json={})
    repo = object.__new__(FinnV2RuntimeContractRepository)
    repo._required_for_update = AsyncMock(return_value=row)

    async def write_revision(*, row, state):
        row.state_json = state
        return row

    repo._write_revision = write_revision
    with pytest.raises(RuntimeContractConflictError, match="owner_or_conversation_missing"):
        asyncio.run(repo.record_responses_clarification(
            run_id="run-7", user_id=8, original_message="Beoordeel mijn plan",
            question="Welke setup bedoel je?", reason="choice_required",
        ))
    result = asyncio.run(repo.record_responses_clarification(
        run_id="run-7", user_id=7, original_message="Beoordeel mijn plan",
        question="Welke setup bedoel je?", reason="choice_required",
    ))
    assert result.state_json["responses_clarification"] == {
        "original_message": "Beoordeel mijn plan",
        "question": "Welke setup bedoel je?",
        "reason": "choice_required",
        "conversation_id": "conv-7",
        "run_id": "run-7",
    }


def test_responses_cursor_rejects_stale_conversation_turn():
    row = SimpleNamespace(last_run_id="new-run", context_json={})
    repo = object.__new__(FinnV2ConversationRepository)
    repo.get_by_id_for_user = AsyncMock(return_value=row)
    repo._flush_with_rollback = AsyncMock()
    with pytest.raises(RuntimeContractConflictError, match="stale_or_unowned"):
        asyncio.run(repo.set_responses_cursor(
            conversation_id="conv-1", user_id=7, run_id="old-run", response_id="resp-old",
        ))
    asyncio.run(repo.set_responses_cursor(
        conversation_id="conv-1", user_id=7, run_id="new-run", response_id="resp-new",
    ))
    assert row.context_json["responses_cursor"] == {"run_id": "new-run", "response_id": "resp-new"}


def test_read_answer_requires_independent_evidence_verification():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=False, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult(
        "De koers is zeker gestegen.", "resp-1", ({
            "status": "completed", "result": {"results": [{
                "scope": "read_market_snapshot", "status": "unavailable", "source": "provider",
                "asset": "AAPL", "as_of": None, "freshness": "unknown", "availability": "unavailable",
                "data": None, "reason": "market_snapshot_missing",
            }]},
        },),
    )
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat doet AAPL nu?", result=result,
    ))
    assert answer.status == "unavailable"
    assert "gestegen" not in answer.text
    assert answer.evidence[0]["asset"] == "AAPL"
    semantic.verify_async.return_value = SimpleNamespace(available=True, passes=True, reason_codes=[])
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat doet AAPL nu?", result=result,
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["compact_evidence"][0]["reason"] == "market_snapshot_missing"


def test_general_education_is_verified_without_personal_read_scope():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat betekent RSI in algemene zin?",
        result=FinnResponsesResult("RSI is een technische indicator.", "resp-1", ({
            "name": "answer_directly", "status": "completed", "result": {"results": []},
        },)),
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["mode"] == "EXPLAIN"
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"]["general_education_no_personal_claims"]


def test_confirmed_action_result_is_grounding_for_saved_object_readback():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Welke setup heb ik net opgeslagen?",
        result=FinnResponsesResult("Je hebt Build Smoke BTC opgeslagen.", "resp-1", ({
            "name": "get_decision_history", "status": "partial",
            "result": {"results": [{"scope": "read_latest_report", "status": "unavailable"}]},
        },)),
        recent_action_result={
            "owner_user_id": 7, "result_status": "succeeded", "operation_id": "create_setup",
            "entity_type": "setup", "canonical_name": "Build Smoke BTC", "entity_id": 42,
        },
    ))
    assert answer.status == "completed"
    evidence = semantic.verify_async.await_args.kwargs["compact_evidence"]
    confirmed = next(item for item in evidence if item["scope"] == "confirmed_action_result")
    assert confirmed["data"]["canonical_name"] == "Build Smoke BTC"
    assert "entity_id" not in confirmed["data"]
    assert "confirmed_action_result" in semantic.verify_async.await_args.kwargs["deterministic_summary"]["available_scopes"]


def test_rejected_read_is_rewritten_once_via_responses_and_reverified():
    semantic = SimpleNamespace(verify_async=AsyncMock(side_effect=[
        SimpleNamespace(available=True, passes=False, reason_codes=["unsupported_market_claim"]),
        SimpleNamespace(available=True, passes=True, reason_codes=[]),
    ]))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="Ik heb geen actuele AAPL-koers om dit te beoordelen."),
    )))
    result = FinnResponsesResult("AAPL stijgt zeker.", "resp-1", ({
        "status": "partial", "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "asset": "AAPL",
            "source": "provider", "as_of": None, "reason": "market_snapshot_missing",
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Wat doet AAPL?", result=result,
    ))
    assert answer.status == "completed"
    assert answer.text == "Ik heb geen actuele AAPL-koers om dit te beoordelen."
    assert semantic.verify_async.await_count == 2
    assert client.responses.create.await_args.kwargs["tool_choice"] == "none"


def test_rewrite_cannot_override_second_verifier_rejection():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_market_claim"],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="AAPL stijgt zeker."),
    )))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Wat doet AAPL?", result=FinnResponsesResult("AAPL stijgt.", "resp-1", ()),
    ))
    assert answer.status == "unavailable"
    assert semantic.verify_async.await_count == 2


def test_unsupported_asset_quantity_is_rewritten_without_repeating_rejected_draft():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text="De strategie heeft een basisbedrag van 100, zonder opgegeven valuta."),
    )))
    result = FinnResponsesResult("Zet 100 BTC in.", "resp-1", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_linked_strategy", "status": "completed", "asset": "BTC",
            "data": {"base_amount": 100},
        }]},
    },))
    verifier = FinnResponsesAnswerVerifier(semantic, client)
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    answer = asyncio.run(verifier.verify(
        message="Waarom past dit plan?", result=result,
    ))
    assert answer.status == "completed"
    assert "100 BTC" not in answer.text
    assert "rejected_draft" not in client.responses.create.await_args.kwargs["input"]


def test_previous_unavailable_source_cannot_be_explained_with_invented_outage():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    client = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock(
        return_value=SimpleNamespace(output_text='{"unsupported_cause": true}'),
    )))
    previous = {
        "run_id": "prior-run", "answer": "Ik heb geen actuele koers.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic, client).verify(
        message="Waarom?",
        result=FinnResponsesResult("Door een technische storing.", "resp-2", ()),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "storing" not in answer.text
    assert client.responses.create.await_args.kwargs["tool_choice"] == "none"


def test_rejected_follow_up_uses_persisted_previous_evidence_limitation():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_cause"],
    )))
    previous = {
        "run_id": "prior-run", "answer": "Actuele koersen ontbreken.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?", result=FinnResponsesResult("Door een storing.", "resp-2", ()),
        previous_response=previous,
    ))
    assert answer.status == "unavailable"
    assert answer.reason == "source_unavailable"
    assert answer.used_previous_response
    assert "oorzaak" in answer.text


def test_unrelated_previous_market_failure_does_not_override_setup_ambiguity():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["setup_ambiguous"],
    )))
    previous = {
        "answer": "Ik heb geen actuele AAPL-koers.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable", "asset": "AAPL",
        }]}}],
    }
    current = FinnResponsesResult("Ik kan je setup beoordelen.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "partial",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "unavailable",
            "reason": "setup_ambiguous", "asset": "BTC",
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Tell me about my BTC setup", result=current, previous_response=previous,
    ))
    assert answer.status == "clarification_required"
    assert answer.reason == "setup_ambiguous"
    assert answer.text.startswith("I found several setups")


def test_resolved_setup_replaces_prior_ambiguous_evidence_in_follow_up():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["unsupported_claim"],
    )))
    previous = {
        "answer": "Welke BTC-setup bedoel je?",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "unavailable", "reason": "setup_ambiguous",
        }]}}],
    }
    current = FinnResponsesResult("Matrix Strategy Parent is je DCA-setup.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "partial",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed", "reason": None,
            "data": {"name": "Matrix Strategy Parent"},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Matrix Strategy Parent", result=current, previous_response=previous,
    ))
    assert answer.reason != "setup_ambiguous"
    previous_evidence = semantic.verify_async.await_args.kwargs["compact_evidence"][-1]
    assert previous_evidence["data"]["source_evidence"] == []


def test_follow_up_keeps_prior_completed_setup_when_current_read_is_profile():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "answer": "Matrix Update Strategie gebruikt setup Matrix Strategy Update Parent.",
        "tool_trace": [{"result": {"results": [
            {"scope": "read_active_setup", "status": "completed",
             "data": {"name": "Matrix Strategy Update Parent"}},
            {"scope": "read_linked_strategy", "status": "completed",
             "data": {"name": "Matrix Update Strategie"}},
            {"scope": "read_market_snapshot", "status": "unavailable",
             "reason": "source_unavailable"},
        ]}}],
    }
    current = FinnResponsesResult("Je risicoprofiel ontbreekt nog.", "resp-2", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed",
            "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Waarom?", result=current, previous_response=previous,
    ))
    assert answer.status == "completed"
    previous_evidence = semantic.verify_async.await_args.kwargs["compact_evidence"][-1]
    assert {item["scope"] for item in previous_evidence["data"]["source_evidence"]} == {
        "read_active_setup", "read_linked_strategy",
    }


def test_absent_profile_is_verifiable_limitation_not_missing_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("Je risicoprofiel ontbreekt nog; wat past bij jou?", "resp-1", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed",
            "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Gebaseerd op mijn profiel, waar kan je mij mee helpen?", result=result,
    ))
    assert answer.status == "completed"
    assert semantic.verify_async.await_args.kwargs["mode"] == "UNAVAILABLE"
    assert semantic.verify_async.await_args.kwargs["deterministic_summary"]["missing_profile_established"]


def test_prior_completed_profile_is_flattened_for_setup_followup_verification():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    previous = {
        "answer": "Welke setup bedoel je?",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_profile", "status": "completed", "source": "users.ai_preferences",
            "data": {"has_profile": True, "trader_profile": {
                "risk_profiles": ["balanced"], "investment_goals": ["wealth_building"],
            }},
        }]}}],
    }
    current = FinnResponsesResult("Je profiel is balanced; de setup is BTC 4H.", "resp-2", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed", "source": "setups",
            "data": {"name": "BTC Plan", "symbol": "BTC", "timeframe": "4H"},
        }]},
    },))
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="BTC Plan", result=current, previous_response=previous,
    ))
    assert answer.status == "completed"
    compact = semantic.verify_async.await_args.kwargs["compact_evidence"]
    assert any(item.get("scope") == "read_profile" and item.get("lineage") == "previous_verified_run"
               for item in compact)


def test_new_direct_topic_does_not_inherit_previous_unavailable_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("RSI vergelijkt koersbewegingen.", "resp-2", ({
        "name": "answer_directly", "arguments": {"uses_previous_response": False},
        "status": "completed", "result": {"results": []},
    },))
    previous = {
        "answer": "De actuele marktdata ontbreekt.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable",
            "reason": "source_unavailable",
        }]}}],
    }
    answer = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat betekent RSI in algemene zin?", result=result, previous_response=previous,
    ))
    assert answer.status == "completed"
    assert answer.used_previous_response is False
    assert all(
        item.get("scope") != "previous_response"
        for item in semantic.verify_async.await_args.kwargs["compact_evidence"]
    )


def test_saved_amount_does_not_ground_asset_quantity():
    evidence = ({
        "scope": "read_linked_strategy", "status": "completed", "asset": "BTC",
        "data": {"base_amount": 100, "entry": "100"},
    },)
    verifier = FinnResponsesAnswerVerifier()
    assert not verifier._asset_quantities_supported(
        answer="Zet 100 BTC in.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert verifier._asset_quantities_supported(
        answer="Je basisbedrag is 100.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert not verifier._currency_units_supported(
        answer="Je inzet is $100.", message="Wat is mijn plan?", evidence=evidence,
    )
    assert verifier._currency_units_supported(
        answer="Je inzet is €100.", message="Wat is mijn plan?",
        evidence=({**evidence[0], "data": {"base_amount": 100, "currency": "EUR"}},),
    )


def test_responses_loop_accepts_direct_answer_without_tools():
    fake = FakeResponses(response("r1", text="Ik kan je plan uitleggen."))

    async def execute(_call):
        raise AssertionError("no tool requested")

    result = asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
        message="Hallo", instructions="Antwoord helder"
    ))
    assert result.tool_trace == ()
    assert result.text == "Ik kan je plan uitleggen."
    assert fake.requests[0]["tool_choice"] == "required"


def test_previous_verified_answer_is_an_assistant_turn_not_user_instructions():
    fake = FakeResponses(response("r1", text="Omdat de huidige beoordeling ontbreekt."))

    async def execute(_call):
        raise AssertionError("no tool needed")

    asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(
        message="Waarom?", instructions="Explain the verified answer.",
        previous_verified_answer="Je strategie is opgeslagen, maar nog niet beoordeeld.",
    ))
    assert fake.requests[0]["input"] == [
        {"role": "assistant", "content": "Je strategie is opgeslagen, maar nog niet beoordeeld."},
        {"role": "user", "content": "Waarom?"},
    ]


def test_invalid_read_arguments_get_one_schema_bound_repair_call():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "symbol": "BTC", "timeframe": "4H",
        }),)),
        response("r2", calls=(tool_call("c2", "get_active_plan_and_strategy", {
            "asset": "BTC", "timeframe": "4H",
        }),)),
        response("r3", text="Je opgeslagen BTC-plan gebruikt 4H."),
    )

    async def execute(call):
        assert call.inputs == {"asset": "BTC", "timeframe": "4H"}
        return {"status": "completed", "results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "timeframe": "4H"},
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat is mijn BTC-plan?", instructions="Gebruik FINN-tools"))
    assert result.tool_trace[0]["result"]["reason"] == "read_arguments_invalid"
    assert "declared argument names" in result.tool_trace[0]["result"]["instruction"]
    assert result.tool_trace[1]["status"] == "completed"
    assert fake.requests[1]["tool_choice"] == {
        "type": "function", "name": "get_active_plan_and_strategy",
    }


def test_repeated_invalid_read_cannot_consume_lifecycle_in_repair_loop():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_indicator_snapshot", {
            "asset": "BTC", "category": "technical",
        }),)),
        response("r2", calls=(tool_call("c2", "get_indicator_snapshot", {
            "asset": "BTC", "category": "RSI",
        }),)),
        response("r3", text="Ik heb geen geverifieerde actuele indicatorwaarden."),
    )

    async def execute(_call):
        raise AssertionError("invalid arguments must not reach execution")

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat zeggen RSI en MA200 nu?", instructions="Gebruik FINN-tools"))
    assert len(result.tool_trace) == 2
    assert all(item["result"]["reason"] == "read_arguments_invalid"
               for item in result.tool_trace)
    assert fake.requests[2]["tool_choice"] == "none"


def test_ambiguous_setup_read_terminalizes_without_second_provider_round():
    fake = FakeResponses(response("r1", calls=(
        tool_call("c1", "get_active_plan_and_strategy", {}),
    )))

    async def execute(_call):
        return {"status": "partial", "results": [{
            "scope": "read_active_setup", "status": "unavailable",
            "reason": "setup_ambiguous",
        }]}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Welk plan past bij mij?", instructions="Gebruik FINN-feiten"))
    assert len(fake.requests) == 1
    assert result.tool_trace[0]["result"]["results"][0]["reason"] == "setup_ambiguous"
    assert result.text == "A setup choice is required."


def test_direct_answer_is_an_explicit_model_choice_with_no_finn_reads():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate("answer_directly", {}).read_tools == ()
    with pytest.raises(FinnResponsesToolError, match="direct_answer_arguments_invalid"):
        catalog.validate("answer_directly", {"asset": "BTC"})
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "answer_directly", {}),)),
        response("r2", text="RSI vergelijkt recente stijgingen en dalingen."),
    )

    async def execute(call):
        assert call.read_tools == ()
        return {"status": "completed", "results": []}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Wat betekent RSI?", instructions="Antwoord algemeen"))
    assert [call["name"] for call in result.tool_trace] == ["answer_directly"]
    assert fake.requests[0]["tool_choice"] == "required"
    assert "tool_choice" not in fake.requests[1]


def test_direct_answer_boundary_does_not_claim_personal_evidence():
    catalog = FinnResponsesToolCatalog()
    executor = object.__new__(FinnResponsesReadExecutor)
    result = asyncio.run(executor(catalog.validate("answer_directly", {})))
    assert result["results"] == []
    assert "call relevant FINN read tools" in result["evidence_boundary"]
    proposal = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    assert "question about whether an action fits a plan" in proposal["description"]


def test_two_read_rounds_force_a_final_answer_before_the_lifecycle_budget():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "answer_directly", {}),)),
        response("r2", calls=(tool_call("c2", "get_my_profile_and_risk_style", {}),)),
        response("r3", text="Ik kan dit alleen op basis van je profiel beoordelen."),
    )

    async def execute(call):
        return {"status": "completed", "results": [], "tool": call.name}

    result = asyncio.run(FinnResponsesLoop(
        client=SimpleNamespace(responses=fake), executor=execute,
    ).run(message="Past dit bij mij?", instructions="Gebruik bewijs"))
    assert len(result.tool_trace) == 2
    assert fake.requests[2]["tool_choice"] == "none"
    assert fake.requests[2]["max_output_tokens"] == 350


def test_tool_trace_is_checkpointed_before_a_later_provider_failure():
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_my_profile_and_risk_style", {}),)),
        RuntimeError("provider down"),
    )
    checkpoints = []

    async def execute(_call):
        return {"status": "completed", "results": []}

    async def checkpoint(response_id, trace):
        checkpoints.append((response_id, trace))

    with pytest.raises(FinnResponsesError, match="responses_provider_error"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute,
            on_tool_result=checkpoint,
        ).run(message="Wat weet je over mijn profiel?", instructions="Gebruik bewijs"))
    assert checkpoints[0][0] == "r1"
    assert checkpoints[0][1][0]["name"] == "get_my_profile_and_risk_style"


def test_verifier_failure_codes_come_from_typed_tool_evidence_not_model_prose():
    classify = FinnResponsesAnswerVerifier._typed_failure_reason
    assert classify(({"status": "unavailable", "reason": "setup_ambiguous"},)) == "setup_ambiguous"
    assert classify(({"status": "unavailable", "reason": "provider_unavailable"},)) == "source_unavailable"
    assert classify(()) == "no_evidence_available"
    assert classify((
        {"status": "completed"}, {"status": "unavailable", "reason": "source_unavailable"},
    )) == "responses_evidence_not_verified"


def test_responses_provider_timeout_leaves_terminal_persistence_reserve(monkeypatch):
    from backend.services import finn_v2_responses_loop as module

    observed = []

    async def bounded_wait(awaitable, *, timeout):
        awaitable.close()
        observed.append(timeout)
        raise TimeoutError()

    fake = SimpleNamespace(responses=SimpleNamespace(create=AsyncMock()))
    monkeypatch.setattr(module, "remaining_lifecycle_seconds", lambda: 14.0)
    monkeypatch.setattr(module.asyncio, "wait_for", bounded_wait)

    with pytest.raises(FinnResponsesError, match="responses_provider_timeout"):
        asyncio.run(FinnResponsesLoop(client=fake, executor=AsyncMock()).run(
            message="Wat weet je?", instructions="Gebruik bewijs",
        ))
    assert observed == [10.5]


def test_responses_loop_bounds_tool_rounds_without_silent_answer():
    fake = FakeResponses(response("r1", calls=(tool_call("c1", "get_active_asset_context", {}),)))

    async def execute(_call):
        return {"status": "completed"}

    with pytest.raises(FinnResponsesError, match="responses_tool_round_limit"):
        asyncio.run(FinnResponsesLoop(
            client=SimpleNamespace(responses=fake), executor=execute, max_rounds=1,
        ).run(message="Welke asset?", instructions="Check feiten"))


def test_responses_loop_rejects_duplicate_call_ids():
    fake = FakeResponses(response("r1", calls=(
        tool_call("c1", "get_active_asset_context", {}),
        tool_call("c1", "get_indicator_snapshot", {}),
    )))

    async def execute(_call):
        return {"status": "completed"}

    with pytest.raises(FinnResponsesError, match="responses_duplicate_call_id"):
        asyncio.run(FinnResponsesLoop(client=SimpleNamespace(responses=fake), executor=execute).run(
            message="Hoe ziet mijn plan eruit?", instructions="Check feiten"
        ))


def test_front_door_prepares_existing_action_pipeline_without_writing():
    fake = FakeResponses(
        response("r1", calls=(tool_call("p1", "create_dca_plan_proposal", {
            "operation_id": "create_setup",
            "inputs": {"setup_type": "dca", "symbol": "BTC", "timeframe": "4H", "name": "DCA test", "dca_frequency": "weekly", "dca_day": "monday"},
        }),)),
        response("r2", text="Ik heb je DCA-concept voorbereid; bevestig nog niets."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()

    async def no_reads(_call):
        raise AssertionError("proposal selection is not a database write")

    front.reads = no_reads
    result = asyncio.run(front.run(
        message="Maak een BTC DCA-setup op 4H met de naam DCA test, wekelijks op maandag.", instructions="Gebruik tools",
        conversation_context={}, verified_asset="BTC",
    ))
    assert result.proposal_analysis.request_plan.operation_id == "create_setup"
    assert result.proposal_analysis.request_plan.operation_state["status"] == "complete"
    assert result.response.tool_trace[0]["result"]["status"] == "validation_pending"


def test_model_read_asset_must_be_explicitly_mentioned_by_user():
    from backend.services.asset_catalog_service import mentioned_catalog_symbols

    assert mentioned_catalog_symbols("Apple en MSFT") == {"AAPL", "MSFT"}
    assert mentioned_catalog_symbols("Wat zeggen RSI en MA200?") == set()
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_indicator_snapshot", {"asset": "AEX"}),)),
        response("r2", text="Ik heb nog geen actuele indicatorwaarden."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    async def read(call):
        received.append(call.inputs)
        return {"status": "completed", "results": []}

    front.reads = read
    asyncio.run(front.run(
        message="Wat zeggen RSI en MA200 samen?", instructions="Gebruik bewijs",
        conversation_context={}, verified_asset=None,
    ))
    assert received == [{}]


def test_plan_read_reference_is_a_typed_model_choice():
    catalog = FinnResponsesToolCatalog()
    assert catalog.validate(
        "get_active_plan_and_strategy", {"reference": "previous_response"},
    ).inputs == {"reference": "previous_response"}
    with pytest.raises(FinnResponsesToolError, match="read_reference_invalid"):
        catalog.validate("get_active_plan_and_strategy", {"reference": "another_user"})


@pytest.mark.parametrize(
    ("asset_name", "message", "symbol"),
    [
        ("Bitcoin", "Beoordeel mijn BTC-handelsplan.", "BTC"),
        ("Apple", "Lees mijn AAPL-plan.", "AAPL"),
        ("Microsoft", "Lees mijn MSFT-plan.", "MSFT"),
    ],
)
def test_model_read_asset_uses_catalog_symbol_after_explicit_mention(asset_name, message, symbol):
    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {"asset": asset_name}),)),
        response("r2", text="Ik lees je plan."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    async def read(call):
        received.append(call.inputs)
        return {"status": "completed", "results": []}

    front.reads = read
    asyncio.run(front.run(
        message=message, instructions="Gebruik bewijs",
        conversation_context={}, verified_asset=symbol,
    ))
    assert received == [{"asset": symbol}]


def test_recent_confirmed_setup_is_bound_server_side_before_read(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {"asset": "BTC"}),)),
        response("r2", text="Je setup gebruikt 100 euro per week."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: True)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["conversation_context"]["previous_action_result"]["entity_id"] == "326"
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Wat zijn frequentie en bedrag van de setup die je net hebt opgeslagen?",
        instructions="Gebruik bewijs", verified_asset="BTC",
        conversation_context={"previous_action_result": {
            "owner_user_id": 21, "result_status": "succeeded", "entity_type": "setup", "entity_id": "326",
        }},
    ))
    assert received == [{"setup_id": 326}]


@pytest.mark.parametrize("read_arguments", [
    {"reference": "previous_response"},
    {"setup_name": "Mijn BTC-setup"},
])
def test_previous_setup_read_reference_is_owner_scoped_and_server_resolved(monkeypatch, read_arguments):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            **read_arguments,
        }),)),
        response("r2", text="Omdat je gekozen setup op 4H werkt."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-21"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": []}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["conversation_context"]["canonical_entity_target"] == {
                "entity_type": "setup", "entity_id": 326,
            }
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Waarom?", instructions="Gebruik bewijs", verified_asset="BTC",
        conversation_context={}, previous_response={
            "answer": "Je gekozen setup gebruikt 4H.",
            "tool_trace": [{"result": {"results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 326, "name": "Mijn BTC-setup"},
            }]}}],
        },
    ))
    assert received == [{"setup_id": 326}]


def test_setup_choice_resolves_user_name_when_model_points_at_clarification(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response", "setup_name": "Matrix Strategy",
        }),)),
        response("r2", text="Je gekozen setup heet Matrix Strategy Update Parent."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-choice"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 326, "name": "Matrix Strategy Update Parent"},
            }]}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: False)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["user_id"] == 21
            assert kwargs["message"] == "Matrix Strategy Update Parent"
            return SimpleNamespace(resolution_status="resolved", entity_id=326)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Matrix Strategy Update Parent", instructions="Gebruik bewijs",
        verified_asset="BTC", conversation_context={}, resuming_clarification=True,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert received == [{"setup_id": 326}]


def test_previous_response_reference_uses_confirmed_owner_scoped_setup_result(monkeypatch):
    import backend.services.finn_v2_responses_front_door as front_module

    fake = FakeResponses(
        response("r1", calls=(tool_call("c1", "get_active_plan_and_strategy", {
            "reference": "previous_response",
        }),)),
        response("r2", text="De laatst opgeslagen setup gebruikt 200 per week."),
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=fake)
    front.user_id = 21
    front.run_id = "run-latest"
    front.proposals = FinnResponsesProposalSelection()
    received = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def commit(self):
            pass

    class Reads:
        session_factory = Session

        async def __call__(self, call):
            received.append(call.inputs)
            return {"status": "completed", "results": [{
                "scope": "read_active_setup", "status": "completed",
                "data": {"setup_id": 327, "name": "Latest", "min_investment": 200},
            }]}

    class Resolver:
        is_setup_collection_request = staticmethod(lambda _message: False)
        references_recent_action = staticmethod(lambda _message, _entity_type: True)

        def __init__(self, _session):
            pass

        async def resolve_canonical_target(self, **kwargs):
            assert kwargs["conversation_context"]["canonical_entity_target"]["entity_id"] == "327"
            return SimpleNamespace(resolution_status="resolved", entity_id=327)

    monkeypatch.setattr(front_module, "FinnV2EntityResolutionService", Resolver)
    monkeypatch.setattr(front_module.FinnV2RuntimeContractRepository, "record_responses_progress", AsyncMock())
    front.reads = Reads()
    asyncio.run(front.run(
        message="Wat is het bedrag van de setup die ik net heb opgeslagen?",
        instructions="Gebruik bewijs", verified_asset="BTC", conversation_context={
            "previous_action_result": {
                "owner_user_id": 21, "result_status": "succeeded",
                "entity_type": "setup", "entity_id": "327",
            },
        },
    ))
    assert received == [{"setup_id": 327}]


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Wat zijn frequentie en bedrag van de setup die je net hebt opgeslagen?", True),
        ("What did you just save in this setup?", True),
        ("Was hast du in diesem Setup gerade gespeichert?", True),
        ("Was kann ich über meinen BTC-Plan sagen?", False),
        ("Welke BTC setups heb ik?", False),
    ],
)
def test_recent_setup_reference_does_not_capture_general_plan_reads(message, expected):
    from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService

    assert FinnV2EntityResolutionService.references_recent_action(message, "setup") is expected


def test_responses_money_claims_require_current_or_immediate_verified_evidence():
    verifier = FinnResponsesAnswerVerifier()
    evidence = ({"scope": "read_market_snapshot", "status": "unavailable"},)
    assert not verifier._amounts_supported(
        answer="Du investierst 150 Euro pro Woche.", message="Was ist mein BTC-Plan?",
        previous_answer="Für die Bewertung fehlen aktuelle Daten.", evidence=evidence,
    )
    assert verifier._amounts_supported(
        answer="Du investierst 100 Euro pro Woche.", message="Was ist mein BTC-Plan?",
        previous_answer="De opgeslagen setup gebruikt €100 per week.", evidence=evidence,
    )
    assert verifier._amounts_supported(
        answer="Het budget is €1.000,00.", message="Wat is het botbudget?",
        previous_answer="", evidence=({
            "scope": "read_bot_status", "status": "completed", "data": {"budget": 1000},
        },),
    )


def test_responses_verifier_blocks_stale_saved_amount_even_if_semantic_model_passes():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    result = FinnResponsesResult("De setup gebruikt €150 per week.", "resp-amount", ({
        "name": "get_market_snapshot", "status": "partial",
        "result": {"results": [{
            "scope": "read_market_snapshot", "status": "unavailable", "reason": "source_unavailable",
        }]},
    },))
    verified = asyncio.run(FinnResponsesAnswerVerifier(semantic).verify(
        message="Wat kan ik veilig zeggen over mijn BTC-plan?",
        result=result, previous_response={"answer": "Er ontbreekt actuele marktdata."},
    ))
    assert verified.status == "unavailable"
    assert verified.reason == "responses_evidence_not_verified"
    assert "150" not in verified.text
    semantic.verify_async.assert_awaited_once()


def test_recent_action_result_query_orders_by_execution_not_contract_revision():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(
        scalars=lambda: [SimpleNamespace(state_json={"action_result": {
            "owner_user_id": 21, "entity_id": "327", "result_status": "succeeded",
            "created_at": "2026-09-24T10:05:00+00:00",
        }}), SimpleNamespace(state_json={"action_result": {
            "owner_user_id": 21, "entity_id": "326", "result_status": "succeeded",
            "created_at": "2026-09-24T10:00:00+00:00",
        }})],
    )))
    repository = FinnV2RuntimeContractRepository(session)
    latest = asyncio.run(repository.get_latest_action_result_for_conversation(
        conversation_id="conv-1", user_id=21,
    ))
    assert latest.state_json["action_result"]["entity_id"] == "327"
    ordering = str(session.execute.await_args.args[0].compile(
        compile_kwargs={"literal_binds": True},
    )).split("ORDER BY", 1)[1]
    assert "action_result" in ordering and "created_at" in ordering
    assert ordering.index("created_at") < ordering.index("updated_at")


@pytest.mark.parametrize(
    ("answer", "unsupported", "expected"),
    [
        ("Je stop-loss is 90 en je target is 120.", False, True),
        ("Deze aanpassing is cruciaal om jouw investeringsdoel te bereiken.", True, False),
    ],
)
def test_personal_advice_audit_uses_typed_evidence(answer, unsupported, expected):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": unsupported,
    }))
    create = AsyncMock(return_value=response)
    client = SimpleNamespace(responses=SimpleNamespace(create=create))
    verifier = FinnResponsesAnswerVerifier(client=client)
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer=answer,
        evidence=[{"scope": "read_active_strategy", "status": "completed", "data": {
            "stop_loss": 90, "targets": [120],
        }}],
        remaining=20,
    ))
    assert actual is expected
    kwargs = create.await_args.kwargs
    assert kwargs["model"] == "gpt-4o"
    assert kwargs["text"]["format"]["type"] == "json_schema"
    assert kwargs["tool_choice"] == "none"
    assert "read_active_strategy" in kwargs["input"]


def test_personal_advice_audit_excludes_superseded_chat_and_draft_evidence():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    result = FinnResponsesResult("De nieuwe setup heet Nieuw en gebruikt 200.", "resp-new", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "Nieuw", "min_investment": 200},
        }]},
    },))
    previous = {
        "answer": "De oude draft heet Oud en gebruikt 100.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "Oud", "min_investment": 100},
        }]}}],
    }
    verified = asyncio.run(verifier.verify(
        message="Wat heb je net opgeslagen?", result=result, previous_response=previous,
    ))
    assert verified.status == "completed"
    audit_evidence = verifier._personal_advice_is_grounded.await_args.kwargs["evidence"]
    assert [item["data"]["name"] for item in audit_evidence] == ["Nieuw"]


def test_short_explanation_audits_immediately_previous_verified_owner_read():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=True)
    previous = {
        "answer": "BTC Plan bewaart instap 100; passendheid is nog niet beoordeeld.",
        "tool_trace": [{"result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "entry": 100},
        }]}}],
    }
    result = FinnResponsesResult("Omdat die instap slechts een opgeslagen instelling is.",
                                 "resp-followup", ({
                                     "name": "answer_directly", "status": "completed",
                                     "arguments": {"uses_previous_response": True},
                                     "result": {"results": []},
                                 },))
    answer = asyncio.run(verifier.verify(
        message="Waarom?", result=result, previous_response=previous,
    ))
    assert answer.status == "completed"
    audit_evidence = verifier._personal_advice_is_grounded.await_args.kwargs["evidence"]
    assert any(item.get("scope") == "read_active_setup" and
               item.get("lineage") == "previous_verified_run" for item in audit_evidence)


def test_missing_profile_limitation_does_not_trigger_personal_advice_audit():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=False)
    result = FinnResponsesResult("Je profiel is nog niet ingevuld.", "resp-profile", ({
        "name": "get_my_profile_and_risk_style", "status": "completed",
        "result": {"results": [{
            "scope": "read_profile", "status": "completed", "data": {"has_profile": False},
        }]},
    },))
    answer = asyncio.run(verifier.verify(message="Wat past bij mijn profiel?", result=result))
    assert answer.status == "completed"
    verifier._personal_advice_is_grounded.assert_not_awaited()


def test_unsupported_personal_advice_rewrite_gets_typed_rejection_reason():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "De opgeslagen setup heet BTC Plan. Ik kan de passendheid nog niet beoordelen."
    create = AsyncMock(return_value=SimpleNamespace(output_text=rewrite))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._personal_advice_is_grounded = AsyncMock(side_effect=[False, True])
    result = FinnResponsesResult("Deze setup past bij jouw risicoprofiel.", "resp", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan"},
        }]},
    },))
    answer = asyncio.run(verifier.verify(message="Past dit?", result=result))
    assert answer.status == "completed"
    assert answer.text == rewrite
    assert "personal_advice_not_grounded" in create.await_args.kwargs["input"]
    assert "three plain sentences" in create.await_args.kwargs["instructions"]


def test_resolved_setup_choice_verifies_original_request_not_prior_question():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic)
    result = FinnResponsesResult("De gekozen setup is BTC 4H.", "resp-choice", ({
        "name": "get_active_plan_and_strategy", "status": "completed",
        "result": {"results": [{
            "scope": "read_active_setup", "status": "completed",
            "data": {"name": "BTC Plan", "symbol": "BTC", "timeframe": "4H"},
        }]},
    },))
    message = "Original user request: Wat is mijn plan?\nUser's chosen answer: BTC Plan"
    answer = asyncio.run(verifier.verify(
        message=message, result=result,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert answer.status == "completed"
    kwargs = semantic.verify_async.await_args.kwargs
    assert kwargs["mode"] == "READ"
    assert kwargs["user_message"] == message
    assert all(item["scope"] != "previous_response" for item in kwargs["compact_evidence"])
    assert "permitted_limited_answer" in kwargs["deterministic_summary"]
    assert "missing_profile_established" not in kwargs["deterministic_summary"]
    assert "IS a complete, safe answer" in kwargs["verification_guidance"]


@pytest.mark.parametrize(
    ("unsupported", "addresses", "expected"),
    [(False, True, True), (False, False, False), (True, True, False)],
)
def test_personal_advice_audit_checks_safety_and_original_question(
    unsupported, addresses, expected,
):
    response = SimpleNamespace(output_text=json.dumps({
        "unsupported_personal_advice": unsupported,
        "addresses_request": addresses,
    }))
    create = AsyncMock(return_value=response)
    verifier = FinnResponsesAnswerVerifier(
        client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    actual = asyncio.run(verifier._personal_advice_is_grounded(
        answer="De opgeslagen setup is bekend; passendheid is nog niet beoordeeld.",
        evidence=[{"scope": "read_active_setup", "status": "completed",
                   "data": {"name": "BTC Plan"}}],
        question="Wat is een logisch plan voor mij? BTC Plan",
        remaining=20,
    ))
    assert actual is expected
    assert "Wat is een logisch plan" in create.await_args.kwargs["input"]


def test_unavailable_technical_read_rewrites_unverified_cause_and_wrong_rsi_fact():
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=True, reason_codes=[],
    )))
    rewrite = "Ik heb geen actuele RSI- of MA200-waarden, dus ik kan ze nu niet samen duiden."
    create = AsyncMock(return_value=SimpleNamespace(output_text=rewrite))
    verifier = FinnResponsesAnswerVerifier(
        semantic=semantic, client=SimpleNamespace(responses=SimpleNamespace(create=create)),
    )
    verifier._technical_limitation_is_grounded = AsyncMock(side_effect=[False, True])
    result = FinnResponsesResult("Door een tijdelijke storing ontbreekt RSI; onder 30 is overbought.",
                                 "resp", ({"name": "get_current_technical_snapshot",
                                           "status": "partial", "result": {"results": [{
                                               "scope": "read_technical_snapshot", "status": "unavailable",
                                               "reason": "source_unavailable",
                                           }]}},))
    answer = asyncio.run(verifier.verify(message="Wat zeggen RSI en MA200 samen?", result=result))
    assert answer.status == "completed"
    assert answer.text == rewrite
    assert verifier._technical_limitation_is_grounded.await_count == 2
    assert "technical_claim_not_grounded" in create.await_args.kwargs["input"]


@pytest.mark.parametrize(("audit_passes", "expected_status"), [
    (True, "completed"), (False, "unavailable"),
])
def test_resolved_choice_requires_strong_grounding_even_when_semantic_rejects(
    audit_passes, expected_status,
):
    semantic = SimpleNamespace(verify_async=AsyncMock(return_value=SimpleNamespace(
        available=True, passes=False, reason_codes=["response_scope_incomplete"],
    )))
    verifier = FinnResponsesAnswerVerifier(semantic=semantic, client=SimpleNamespace())
    verifier._personal_advice_is_grounded = AsyncMock(return_value=audit_passes)
    result = FinnResponsesResult(
        "De opgeslagen setup heet BTC Plan. Of deze bij je past is nog niet beoordeeld.",
        "resp-choice", ({"name": "get_active_plan_and_strategy", "status": "completed",
                         "result": {"results": [{"scope": "read_active_setup",
                                                "status": "completed",
                                                "data": {"name": "BTC Plan"}}]}},),
    )
    message = "Original user request: Wat is een logisch plan voor mij?\nUser's chosen answer: BTC Plan"
    answer = asyncio.run(verifier.verify(
        message=message, result=result,
        previous_response={"answer": "Welke setup bedoel je?", "tool_trace": []},
    ))
    assert answer.status == expected_status
    assert verifier._personal_advice_is_grounded.await_args.kwargs["question"] == message
