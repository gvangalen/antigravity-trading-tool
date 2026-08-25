import pytest

from backend.domain.finn_v2_operation_registry import (
    FinnV2OperationRegistry,
    FinnV2OperationUnavailableError,
    OperationContract,
)
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


def test_registry_manifest_has_one_valid_contract_per_operation():
    registry = FinnV2OperationRegistry()
    contracts = registry.list()

    assert len({contract.operation_id for contract in contracts}) == len(contracts)
    for contract in contracts:
        assert not set(contract.required_scopes).intersection(contract.optional_scopes)
        if contract.supported:
            assert contract.mode


def test_supported_read_contracts_have_canonical_tools_and_no_model_call():
    registry = FinnV2OperationRegistry()

    setup = registry.require_supported("read_active_setup")
    assert setup.model_policy == "never"
    assert setup.tool_names == ("read_active_asset", "read_active_setup")


def test_indicator_read_contract_requires_a_visible_count_and_all_indicator_names():
    contract = FinnV2OperationRegistry().require_supported("read_indicator_configuration")

    assert contract.required_response_fields == ("asset", "configured_count", "indicator_names")


def test_unimplemented_operations_are_capability_gaps_not_executable():
    registry = FinnV2OperationRegistry()

    with pytest.raises(FinnV2OperationUnavailableError, match="create_strategy_execution_adapter_missing"):
        registry.require_supported("create_strategy")


def test_write_contract_requires_confirmable_proposal():
    with pytest.raises(ValueError, match="write_contract_incomplete"):
        OperationContract(
            operation_id="bad_write",
            version="test",
            domain="test",
            mode="CREATE_PROPOSAL",
            aliases=(),
        )


def test_contract_rejects_an_input_that_is_both_required_and_optional():
    with pytest.raises(ValueError, match="input_overlap"):
        OperationContract(
            operation_id="bad_inputs",
            version="test",
            domain="test",
            mode="READ",
            aliases=(),
            required_inputs=("asset",),
            optional_inputs=("asset",),
        )


def test_contract_rejects_unknown_required_response_field():
    with pytest.raises(ValueError, match="unknown_response_field"):
        OperationContract(
            operation_id="bad_response_contract",
            version="test",
            domain="test",
            mode="READ",
            aliases=(),
            required_response_fields=("unknown_graph_node",),
        )


def test_registry_is_the_complete_mode_scope_and_tool_source_for_new_requests():
    service = FinnV2RequestAnalysisService()
    cases = [
        ("Hoi FINN, wat kun je voor mij doen?", "capability"),
        ("Welke setup staat voor BTC actief?", "read_active_setup"),
        ("Welke indicatoren staan voor BTC ingesteld?", "read_indicator_configuration"),
        ("Bekijk mijn profiel, indicatoren, setup, strategie en bot. Wat ontbreekt?", "evaluate_plan"),
        ("Maak een setup voor BTC swing trading.", "create_setup"),
        ("Voeg ETH toe aan mijn watchlist.", "watchlist_add"),
    ]
    registry = FinnV2OperationRegistry()

    for message, operation_id in cases:
        analysis = service.analyze(message=message)
        contract = registry.require_supported(operation_id)

        assert analysis.request_plan.operation_id == contract.operation_id
        assert analysis.interaction_mode == contract.mode
        assert analysis.request_plan.required_information_scopes == list(contract.required_scopes)
        assert analysis.request_plan.optional_information_scopes == list(contract.optional_scopes)


def test_all_deterministic_read_contracts_are_explicitly_provider_free():
    registry = FinnV2OperationRegistry()

    deterministic_reads = [
        contract
        for contract in registry.list()
        if contract.supported and contract.mode in {"CAPABILITY", "READ", "UNAVAILABLE", "CLARIFICATION"}
    ]

    assert deterministic_reads
    assert all(contract.model_policy == "never" for contract in deterministic_reads)


def test_workflow_contracts_are_not_business_execution_adapters():
    registry = FinnV2OperationRegistry()

    confirmation = registry.require_supported("confirm_proposal")
    execution = registry.require_supported("execute_proposal")

    assert confirmation.execution_adapter is None
    assert confirmation.proposal_type == "confirmation"
    assert execution.execution_adapter is None
    assert execution.proposal_type == "execution"
