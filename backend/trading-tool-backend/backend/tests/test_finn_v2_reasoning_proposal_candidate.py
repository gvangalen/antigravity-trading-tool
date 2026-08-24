from datetime import datetime, timezone

import pytest

from backend.schemas.finn_v2_reasoning_context_schema import ReasoningContextPackage, ReasoningEvidenceItem, ReasoningPolicyContext
from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
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


def test_complete_proposal_contracts_remain_deterministic():
    service = FinnV2ReasoningService(session=object())
    contract = FinnV2OperationRegistry().require_supported("create_setup")

    assert contract.response_strategy == "proposal_draft"
    assert contract.model_policy == "optional"
    assert service._uses_deterministic_contract_response(contract) is True
    assert service._uses_deterministic_contract_response(
        FinnV2OperationRegistry().require_supported("evaluate_plan")
    ) is False
