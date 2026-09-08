from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage, ReasoningEvidenceItem, ReasoningPolicyContext
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.schemas.finn_v2_proposal_schema import (
    BotActivationChange,
    BotChange,
    IndicatorConfigurationChange,
    WatchlistChange,
)
from backend.schemas.finn_v2_reasoning_schema import ProposalCandidate, ReasoningResult
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService


def test_reasoning_proposal_candidate_must_match_allowed_operation():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-1",
        user_id=7,
        user_message="Voeg DXY toe",
        locale="nl-NL",
        interaction_mode="PROPOSAL",
        orchestrator_result_id="o-1",
        snapshot_id="s-1",
        validation_id="v-1",
        policy_decision_id="p-1",
        evidence_set_hash="hash",
        evidence=[ReasoningEvidenceItem(evidence_id="E1", artifact_id="a1", tool_name="read_indicator_configuration", domain="market_context", entity_type="indicator_configuration", source="internal", freshness="unknown", confidence="high")],
        policy=ReasoningPolicyContext(policy_class="proposal", allowed=True, proposal_allowed=True, confirmation_required=True, step_up_required=False, execution_allowed=False, operation_type="update_indicator_configuration"),
        allowed_operation_types=["update_indicator_configuration"],
    )
    result = ReasoningResult(
        reasoning_result_id="r-1",
        run_id="run-1",
        user_id=7,
        mode="PROPOSAL",
        direct_answer="Conceptvoorstel.",
        main_observation="DXY ontbreekt.",
        claims=[],
        proposal_candidate=ProposalCandidate(
            operation_type="activate_live_bot",
            target_type="bot",
            proposed_changes={"mode": "live"},
            impact_summary="impact",
            risk_summary="risk",
            confirmation_required=True,
        ),
        evidence_refs_used=["E1"],
        model="gpt-test",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(ValueError):
        service._validate_refs(result, context)


def test_deterministic_proposal_contract_creates_one_missing_field_clarification_without_provider():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-guided-setup",
        user_id=406,
        user_message="Help me een nieuwe BTC-setup als concept te maken.",
        locale="nl-NL",
        interaction_mode="CREATE_PROPOSAL",
        orchestrator_result_id="o-guided-setup",
        snapshot_id="s-guided-setup",
        validation_id="v-guided-setup",
        policy_decision_id="p-guided-setup",
        evidence_set_hash="guided-setup-hash",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="Easset",
                artifact_id="asset-guided-setup",
                tool_name="read_active_asset",
                information_scope="active_asset",
                domain="identity_context",
                entity_type="asset",
                asset="BTC",
                source="workspace",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "BTC"},
            )
        ],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type="create_setup",
        ),
        request_plan={
            "operation_id": "create_setup",
            "operation_state": {
                "collected_inputs": {"symbol": "BTC", "setup_type": "trade"},
                "missing_required_inputs": ["name"],
                "next_missing_input": "name",
            },
        },
    )

    result = service._deterministic_contract_draft(
        contract=FinnV2OperationRegistry().require_supported("create_setup"),
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
    )

    assert result.mode == "CLARIFICATION"
    assert result.follow_up_question
    assert result.proposal_candidate is None


def test_deterministic_setup_proposal_uses_completed_typed_state_without_write():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-guided-setup-complete",
        user_id=406,
        user_message="Noem hem BTC Daily 4H concept.",
        locale="nl-NL",
        interaction_mode="CREATE_PROPOSAL",
        orchestrator_result_id="o-guided-setup",
        snapshot_id="s-guided-setup",
        validation_id="v-guided-setup",
        policy_decision_id="p-guided-setup",
        evidence_set_hash="guided-setup-hash",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="Easset",
                artifact_id="asset-guided-setup",
                tool_name="read_active_asset",
                information_scope="active_asset",
                domain="identity_context",
                entity_type="asset",
                asset="BTC",
                source="workspace",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "BTC"},
            )
        ],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type="create_setup",
        ),
        request_plan={
            "operation_id": "create_setup",
            "operation_state": {
                "collected_inputs": {
                    "name": "BTC Daily 4H concept",
                    "symbol": "BTC",
                    "setup_type": "trade",
                    "timeframe": "4H",
                },
                "missing_required_inputs": [],
            },
        },
    )

    result = service._deterministic_contract_draft(
        contract=FinnV2OperationRegistry().require_supported("create_setup"),
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
    )

    assert result.mode == "CREATE_PROPOSAL"
    assert result.proposal_candidate is not None
    assert result.proposal_candidate.proposed_changes["proposal_status"] == "draft"
    assert result.proposal_candidate.proposed_changes["setup_fields"]["name"] == "BTC Daily 4H concept"
    assert "4H" in result.direct_answer


def test_deterministic_asset_selection_proposal_uses_registry_input_without_provider():
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id="run-select-asset",
        user_id=406,
        user_message="Selecteer Solana als mijn actieve asset.",
        locale="nl-NL",
        interaction_mode="ACTION_PROPOSAL",
        orchestrator_result_id="o-select-asset",
        snapshot_id="s-select-asset",
        validation_id="v-select-asset",
        policy_decision_id="p-select-asset",
        evidence_set_hash="select-asset-hash",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="Eactive",
                artifact_id="asset-select-asset",
                tool_name="read_active_asset",
                information_scope="active_asset",
                domain="identity_context",
                entity_type="asset",
                asset="BTC",
                source="workspace",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "BTC"},
            )
        ],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type="select_asset",
        ),
        request_plan={
            "operation_id": "select_asset",
            "target_asset": "SOL",
            "operation_state": {
                "collected_inputs": {},
                "missing_required_inputs": [],
            },
        },
    )

    result = service._deterministic_contract_draft(
        contract=FinnV2OperationRegistry().require_supported("select_asset"),
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
    )

    assert result.mode == "ACTION_PROPOSAL"
    assert result.proposal_candidate is not None
    assert result.proposal_candidate.operation_type == "select_asset"
    assert result.proposal_candidate.asset == "SOL"
    assert result.proposal_candidate.proposed_changes["asset"] == "SOL"
    assert result.proposal_candidate.evidence_refs == ["Eactive"]
    assert result.reasoning_provenance["operation_id"] == "select_asset"


def test_deterministic_proposals_find_active_asset_by_contract_scope_not_tool_name():
    service = FinnV2ReasoningService(session=object())
    evidence = ReasoningEvidenceItem(
        evidence_id="Eident",
        artifact_id="asset-contract-scope",
        tool_name="read_active_asset",
        information_scope="active_asset",
        domain="identity_context",
        entity_type="asset",
        asset="BTC",
        source="workspace",
        freshness="fresh",
        confidence="high",
        facts={"symbol": "BTC"},
    )
    # The persisted scope is canonical; the delivery label is not an authority.
    evidence.tool_name = "identity_context_projection"
    context = ReasoningContextPackage(
        run_id="run-contract-scope",
        user_id=406,
        user_message="Maak een BTC-swing setup met timeframe 4H en naam Contract scope.",
        locale="nl-NL",
        interaction_mode="CREATE_PROPOSAL",
        orchestrator_result_id="o-contract-scope",
        snapshot_id="s-contract-scope",
        validation_id="v-contract-scope",
        policy_decision_id="p-contract-scope",
        evidence_set_hash="contract-scope-hash",
        evidence=[evidence],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type="create_setup",
        ),
        request_plan={
            "operation_id": "create_setup",
            "operation_state": {
                "collected_inputs": {
                    "name": "Contract scope",
                    "symbol": "BTC",
                    "setup_type": "swing",
                    "timeframe": "4H",
                },
                "missing_required_inputs": [],
            },
        },
    )

    result = service._deterministic_contract_draft(
        contract=FinnV2OperationRegistry().require_supported("create_setup"),
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
    )

    assert result.proposal_candidate is not None
    assert result.proposal_candidate.evidence_refs == ["Eident"]


def test_complete_proposal_contracts_remain_deterministic():
    service = FinnV2ReasoningService(session=object())
    contract = FinnV2OperationRegistry().require_supported("create_setup")

    assert contract.response_strategy == "proposal_draft"
    assert contract.model_policy == "optional"
    assert service._uses_deterministic_contract_response(contract) is True
    assert service._uses_deterministic_contract_response(
        FinnV2OperationRegistry().require_supported("evaluate_plan")
    ) is False


@pytest.mark.parametrize(
    ("operation_id", "inputs", "target_type"),
    [
        ("create_indicator_configuration", {"asset": "SOL", "category": "momentum", "indicator": "RSI"}, "indicator_configuration"),
        ("update_indicator_configuration", {"asset": "SOL", "category": "momentum", "indicator": "RSI", "changed_fields": {"period": 21}}, "indicator_configuration"),
        ("delete_indicator_configuration", {"asset": "SOL", "category": "momentum", "indicator": "RSI"}, "indicator_configuration"),
        ("update_setup", {"setup_id": 41, "changed_fields": {"timeframe": "1H"}}, "setup"),
        ("delete_setup", {"setup_id": 41}, "setup"),
        ("create_strategy", {"setup_id": 41, "execution_mode": "fixed", "base_amount": 100}, "strategy"),
        ("update_strategy", {"strategy_id": 52, "changed_fields": {"risk": "low"}}, "strategy"),
        ("delete_strategy", {"strategy_id": 52}, "strategy"),
        ("create_bot", {"strategy_id": 52, "name": "Paper scout"}, "bot"),
        ("update_bot", {"bot_id": 63, "changed_fields": {"name": "Paper scout two"}}, "bot"),
        ("deactivate_bot", {"bot_id": 63}, "bot"),
        ("delete_bot", {"bot_id": 63}, "bot"),
        ("watchlist_remove", {"asset": "SOL"}, "watchlist"),
    ],
)
def test_every_complete_registry_proposal_contract_has_a_deterministic_draft(
    operation_id, inputs, target_type,
):
    service = FinnV2ReasoningService(session=object())
    context = ReasoningContextPackage(
        run_id=f"run-{operation_id}",
        user_id=406,
        user_message="Typed action-contract fixture.",
        locale="en-US",
        interaction_mode=FinnV2OperationRegistry().require_supported(operation_id).mode,
        orchestrator_result_id=f"o-{operation_id}",
        snapshot_id=f"s-{operation_id}",
        validation_id=f"v-{operation_id}",
        policy_decision_id=f"p-{operation_id}",
        evidence_set_hash=f"hash-{operation_id}",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="Efixture",
                artifact_id="fixture",
                tool_name="read_active_asset",
                information_scope="active_asset",
                domain="identity_context",
                entity_type="asset",
                asset="SOL",
                source="fixture",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "SOL"},
            )
        ],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type=operation_id,
        ),
        request_plan={
            "operation_id": operation_id,
            "operation_state": {"collected_inputs": inputs, "missing_required_inputs": []},
        },
    )

    result = service._deterministic_contract_draft(
        contract=FinnV2OperationRegistry().require_supported(operation_id),
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
    )

    assert result.mode == FinnV2OperationRegistry().require_supported(operation_id).mode
    assert result.proposal_candidate is not None
    assert result.proposal_candidate.operation_type == operation_id
    assert result.proposal_candidate.target_type == target_type
    assert result.proposal_candidate.confirmation_required is True


def test_generic_draft_change_projection_uses_the_existing_proposal_union_members():
    service = FinnV2ReasoningService(session=object()).fallbacks
    change_payload = lambda payload: {
        key: value for key, value in payload.items()
        if key not in {"proposal_status", "generation_source"}
    }

    created_indicator = service._proposal_changes(
        operation_id="create_indicator_configuration",
        supplied_inputs={"asset": "SOL", "category": "momentum", "indicator": "RSI"},
        evidence_by_tool={},
    )
    updated_indicator = service._proposal_changes(
        operation_id="update_indicator_configuration",
        supplied_inputs={"asset": "SOL", "category": "momentum", "indicator": "RSI", "changed_fields": {"period": 21}},
        evidence_by_tool={},
    )
    removed_indicator = service._proposal_changes(
        operation_id="delete_indicator_configuration",
        supplied_inputs={"asset": "SOL", "category": "momentum", "indicator": "RSI"},
        evidence_by_tool={},
    )
    watchlist = service._proposal_changes(
        operation_id="watchlist_remove", supplied_inputs={"asset": "SOL"}, evidence_by_tool={}
    )
    bot = service._proposal_changes(
        operation_id="deactivate_bot", supplied_inputs={"bot_id": 63}, evidence_by_tool={}
    )
    paper = service._proposal_changes(
        operation_id="activate_paper_bot",
        supplied_inputs={"bot_id": 63},
        evidence_by_tool={"read_linked_bot": type("Evidence", (), {"facts": {"is_live": False}})()},
    )

    assert IndicatorConfigurationChange.parse_obj(change_payload(created_indicator)).operation == "add"
    assert IndicatorConfigurationChange.parse_obj(change_payload(updated_indicator)).after == {"period": 21}
    assert IndicatorConfigurationChange.parse_obj(change_payload(removed_indicator)).operation == "remove"
    assert WatchlistChange.parse_obj(change_payload(watchlist)).operation == "remove"
    assert BotChange.parse_obj(change_payload(bot)).changed_fields == {"is_active": False}
    assert BotActivationChange.parse_obj(change_payload(paper)).requested_mode == "paper"
