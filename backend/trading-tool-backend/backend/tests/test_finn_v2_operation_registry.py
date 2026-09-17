from types import SimpleNamespace
import json
from pathlib import Path

import pytest

from backend.domain.finn_v2_operation_registry import (
    FinnV2OperationRegistry,
    FinnV2OperationUnavailableError,
    OperationContract,
)
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.domain.finn_v2_runtime_contract import new_runtime_contract_state, record_selection
from backend.domain.finn_v2_setup_input_catalog import FinnV2SetupInputCatalog


def test_registry_manifest_has_one_valid_contract_per_operation():
    registry = FinnV2OperationRegistry()
    contracts = registry.list()

    assert len({contract.operation_id for contract in contracts}) == len(contracts)
    for contract in contracts:
        assert not set(contract.required_scopes).intersection(contract.optional_scopes)
        if contract.supported:
            assert contract.mode


def test_every_declassified_action_acceptance_record_maps_to_one_registry_contract():
    fixture = Path(__file__).parent / "fixtures" / "finn_v2_declassified_34746230528_regression.json"
    records = json.loads(fixture.read_text(encoding="utf-8"))["failures"]
    registry = FinnV2OperationRegistry()

    assert len(records) == 39
    for record in records:
        operation_id = record["expected"]["operation"]
        contract = registry.require_supported(operation_id)
        assert contract.action_polarity.value == record["expected"]["action_polarity"], record["case_id"]


def test_supported_read_contracts_have_canonical_tools_and_no_model_call():
    registry = FinnV2OperationRegistry()

    setup = registry.require_supported("read_active_setup")
    assert setup.model_policy == "never"
    assert setup.tool_names == ("read_active_setup",)


def test_indicator_read_contract_requires_a_visible_count_and_all_indicator_names():
    contract = FinnV2OperationRegistry().require_supported("read_indicator_configuration")

    assert contract.required_response_fields == ("asset", "configured_count", "indicator_names")


def test_completed_v1_strategy_contract_is_a_confirmable_v2_operation():
    registry = FinnV2OperationRegistry()

    contract = registry.require_supported("create_strategy")

    assert contract.mode == "CREATE_PROPOSAL"
    assert contract.required_inputs == (
        "setup_id", "name", "execution_mode", "base_amount",
        "entry", "stop_loss", "targets", "risk_profile",
    )
    assert contract.execution_adapter == "create_strategy"
    assert contract.confirmation_required is True


def test_registry_declares_the_only_contextual_reference_slots_for_action_contracts():
    registry = FinnV2OperationRegistry()

    assert registry.require_supported("update_setup").contextual_reference_inputs == ("setup_id",)
    assert registry.require_supported("create_strategy").contextual_reference_inputs == ("setup_id",)
    assert registry.require_supported("update_strategy").contextual_reference_inputs == ("strategy_id",)
    assert registry.require_supported("create_bot").contextual_reference_inputs == ("strategy_id",)
    assert registry.require_supported("update_bot").contextual_reference_inputs == ("bot_id",)


def test_audited_v1_flows_resolve_only_through_the_canonical_registry():
    """Keep the runtime from reviving a parallel legacy action definition."""
    registry = FinnV2OperationRegistry()

    expected = {
        "create_setup": ("CREATE_PROPOSAL", ("setup_type", "timeframe", "name", "symbol")),
        "evaluate_plan": ("EVALUATE", ()),
        "evaluate_setup": ("EVALUATE", ()),
        "read_indicator_configuration": ("READ", ()),
        "evaluate_bot": ("EVALUATE", ()),
        "create_strategy": (
            "CREATE_PROPOSAL",
            ("setup_id", "name", "execution_mode", "base_amount", "entry", "stop_loss", "targets", "risk_profile"),
        ),
    }

    for operation_id, (mode, required_inputs) in expected.items():
        contract = registry.require_supported(operation_id)
        assert contract.mode == mode
        assert contract.required_inputs == required_inputs

    # ``generate_strategy`` belongs to the legacy generation surface. New V2
    # flows must resolve the single confirmable ``create_strategy`` contract.
    with pytest.raises(FinnV2OperationUnavailableError, match="unknown_operation:generate_strategy"):
        registry.get("generate_strategy")


def test_evaluate_setup_contract_distinguishes_multilingual_assessment_from_reading():
    contract = FinnV2OperationRegistry().require_supported("evaluate_setup")

    assert set(contract.positive_examples) >= {
        "Beoordeel mijn actieve setup.",
        "Evaluate my active setup.",
        "Bewerte mein aktives Setup.",
    }
    assert set(contract.negative_examples) >= {
        "Toon mijn actieve setup.",
        "Show my active setup.",
        "Zeige mein aktives Setup.",
    }


def test_evaluate_strategy_requires_only_the_persisted_strategy_graph():
    contract = FinnV2OperationRegistry().require_supported("evaluate_strategy")

    assert contract.required_scopes == (
        "active_asset", "active_setup", "linked_strategy",
    )
    assert contract.optional_scopes == ("profile", "preferences")
    assert contract.tool_names == (
        "read_active_asset", "read_active_setup", "read_linked_strategy",
    )


def test_create_dca_setup_exposes_its_service_required_frequency_in_the_same_contract():
    contract = FinnV2OperationRegistry().require_supported("create_setup")

    assert contract.required_inputs_for({"setup_type": "trade"}) == contract.required_inputs
    assert contract.required_inputs_for({"setup_type": "dca"}) == (
        "setup_type", "timeframe", "name", "symbol", "dca_frequency",
    )
    assert "dca_frequency" in contract.input_fields
    assert contract.required_inputs_for({"setup_type": "dca", "dca_frequency": "weekly"})[-1] == "dca_day"
    assert contract.required_inputs_for({"setup_type": "dca", "dca_frequency": "monthly"})[-1] == "dca_month_day"


def test_create_dca_setup_binds_weekday_before_proposal_execution():
    contract = FinnV2OperationRegistry().require_supported("create_setup")
    service = FinnV2OperationStateService()
    context = {
        "conversation_state_version": service.CONTEXT_STATE_VERSION,
        "active_guided_operation": {
            "operation_id": "create_setup",
            "contract_version": contract.version,
            "state_revision": 3,
            "collected_inputs": {
                "setup_type": "dca",
                "timeframe": "4H",
                "name": "FINN DCA Flow",
                "symbol": "BTC",
                "dca_frequency": "weekly",
            },
            "input_sources": {},
            "resolved_entities": {},
            "target_entities": {},
            "missing_required_inputs": ["dca_day"],
            "next_missing_input": "dca_day",
            "previous_evidence_refs": [],
        },
    }

    state = service.resolve(
        contract=contract,
        message="maandag",
        explicit_asset=None,
        conversation_context=context,
    )

    assert state.collected_inputs["dca_day"] == "monday"
    assert state.missing_required_inputs == []
    assert state.next_missing_input is None


def test_create_dca_setup_extracts_compound_weekly_schedule_without_polluting_name():
    contract = FinnV2OperationRegistry().require_supported("create_setup")

    supplied = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message=(
            "Maak een wekelijkse DCA-setup voor BTC op 4H met de naam "
            "FINN DCA Live en koop op maandag."
        ),
        explicit_asset="BTC",
    )

    assert supplied["name"] == "FINN DCA Live"
    assert supplied["dca_frequency"] == "weekly"
    assert supplied["dca_day"] == "monday"
    assert contract.required_inputs_for(supplied) == (
        "setup_type", "timeframe", "name", "symbol", "dca_frequency", "dca_day",
    )
    assert FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message="Maak een dagelijkse DCA setup voor SOL op 4 uur met de naam Test.",
        explicit_asset="SOL",
    )["dca_frequency"] == "daily"


def test_create_dca_setup_canonicalizes_a_natural_german_daily_frequency():
    contract = FinnV2OperationRegistry().require_supported("create_setup")

    supplied = FinnV2OperationStateService().explicit_inputs(
        contract=contract,
        message="Erstelle ein taegliches DCA-Setup fuer SOL auf 4 Stunden mit dem Namen Geduldiger Aufbau.",
        explicit_asset="SOL",
    )

    assert supplied["setup_type"] == "dca"
    assert supplied["dca_frequency"] == "daily"


def test_runtime_contract_preserves_registry_conditional_inputs():
    state = new_runtime_contract_state(
        run=SimpleNamespace(
            id="run-1", conversation_id="conversation-1", trace_id="trace-1", user_id=1,
            message="Maak een dagelijkse DCA setup.",
        ),
        contract_id="contract-1",
    )
    state["initial_operation_id"] = "create_setup"
    state["final_operation_id"] = "create_setup"
    projected = record_selection(
        state,
        canonical_target="SOL",
        target_source="explicit_message",
        original_target_text="SOL",
        target_type="asset",
        conversation_reference=None,
        conversation_reference_kind=None,
        supplied_inputs={
            "setup_type": "dca", "timeframe": "4H", "name": "DCA SOL",
            "symbol": "SOL", "dca_frequency": "daily",
        },
    )

    assert projected["supplied_inputs"]["dca_frequency"] == "daily"
    assert projected["missing_inputs"] == []


def test_explicit_setup_duration_wins_over_dca_daily_cadence_word():
    assert FinnV2SetupInputCatalog.timeframe_from_text(
        "Maak een dagelijkse DCA setup voor SOL op 4 uur."
    ) == "4H"


def test_scores_and_portfolio_contracts_use_their_canonical_scopes():
    registry = FinnV2OperationRegistry()

    assert registry.require_supported("read_scores").tool_names == (
        "read_active_asset", "read_asset_scores"
    )
    assert registry.require_supported("explain_score").required_scopes == (
        "active_asset", "scores"
    )
    assert registry.require_supported("read_portfolio").tool_names == ("read_portfolio",)
    assert registry.require_supported("evaluate_portfolio").required_scopes == (
        "portfolio", "profile", "preferences"
    )
    assert registry.require_supported("read_portfolio").optional_inputs == ("asset",)
    assert registry.require_supported("evaluate_portfolio").optional_inputs == ("asset",)


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


def test_contract_rejects_a_contextual_input_that_is_not_a_required_input():
    with pytest.raises(ValueError, match="contextual_input_not_required"):
        OperationContract(
            operation_id="bad_contextual_input",
            version="test",
            domain="test",
            mode="READ",
            aliases=(),
            contextual_reference_inputs=("bot_id",),
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


def test_completed_contract_extensions_have_a_single_confirmed_write_boundary():
    registry = FinnV2OperationRegistry()
    operations = {
        "select_asset": ("asset",),
        "create_indicator_configuration": ("asset", "category", "indicator"),
        "update_indicator_configuration": ("asset", "category", "indicator", "changed_fields"),
        "delete_indicator_configuration": ("asset", "category", "indicator"),
        "delete_setup": ("setup_id",),
        "delete_strategy": ("strategy_id",),
        "create_bot": ("strategy_id", "name"),
        "update_bot": ("bot_id", "changed_fields"),
        "delete_bot": ("bot_id",),
        "deactivate_bot": ("bot_id",),
    }

    for operation_id, required_inputs in operations.items():
        contract = registry.require_supported(operation_id)
        assert contract.required_inputs == required_inputs
        assert contract.proposal_type == operation_id
        assert contract.execution_adapter == operation_id
        assert contract.confirmation_required is True
