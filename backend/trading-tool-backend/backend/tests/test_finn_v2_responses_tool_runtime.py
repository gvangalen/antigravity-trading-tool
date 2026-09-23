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
    assert len(catalog.definitions()) == 13
    proposal = next(item for item in catalog.definitions() if item["name"] == "create_dca_plan_proposal")
    assert proposal["parameters"]["properties"]["payload"]["properties"]["inputs"]["properties"]["min_investment"]["type"] == "number"


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


def test_pending_guided_operation_cannot_be_silently_skipped():
    catalog = FinnResponsesToolCatalog()
    first = FinnResponsesProposalSelection().from_call(
        call=catalog.validate("create_dca_plan_proposal", {
            "operation_id": "create_setup", "inputs": {"setup_type": "dca", "symbol": "BTC"},
        }),
        message="Maak een DCA-setup voor BTC", conversation_context={}, verified_asset="BTC",
    )
    front = object.__new__(FinnResponsesFrontDoor)
    front.client = SimpleNamespace(responses=FakeResponses(response("r1", text="Ik ga verder.")))
    front.user_id = 21
    front.run_id = "run-guided"
    front.proposals = FinnResponsesProposalSelection()
    context = {"active_guided_operation": first.request_plan.operation_state}
    with pytest.raises(FinnResponsesError, match="guided_proposal_tool_call_required"):
        asyncio.run(front.run(
            message="4H", instructions="Vul het gevraagde veld", conversation_context=context,
            verified_asset="BTC",
        ))


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
    assert all(tool["name"] not in {"confirm_proposal", "execute_confirmed_proposal"} for tool in fake.requests[0]["tools"])


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
        message="Maak een BTC DCA-setup met de naam DCA test, wekelijks op maandag.", instructions="Gebruik tools",
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
