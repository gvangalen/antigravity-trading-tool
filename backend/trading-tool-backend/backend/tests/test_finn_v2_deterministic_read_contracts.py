from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.schemas.finn_v2_orchestrator_schema import RequestPlan
from backend.schemas.finn_v2_reasoning_context_schema import (
    ReasoningContextPackage,
    ReasoningEvidenceItem,
    ReasoningPolicyContext,
)
from backend.schemas.finn_v2_response_schema import ResponseDraft
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.services.finn_v2_response_verifier_service import FinnV2ResponseVerifierService


def _context(*, operation_id, required_scope, message, evidence):
    required_scopes = required_scope if isinstance(required_scope, list) else [required_scope]
    return ReasoningContextPackage(
        run_id="run-read-contract",
        user_id=406,
        user_message=message,
        locale="nl-NL",
        interaction_mode="READ",
        subject_scopes=required_scopes,
        required_domains=[],
        orchestrator_result_id="orchestrator-read-contract",
        snapshot_id="snapshot-read-contract",
        validation_id="validation-read-contract",
        policy_decision_id="policy-read-contract",
        evidence_set_hash="read-contract-hash",
        evidence=evidence,
        policy=ReasoningPolicyContext(
            policy_class="read_only",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        request_plan={
            "operation_id": operation_id,
            "required_information_scopes": required_scopes,
        },
    )


@pytest.mark.parametrize(
    ("operation_id", "required_scope", "message", "evidence"),
    [
        (
            "read_active_asset",
            "active_asset",
            "Wat is mijn actieve asset?",
            [
                ReasoningEvidenceItem(
                    evidence_id="Easset",
                    artifact_id="artifact-asset",
                    tool_name="read_active_asset",
                    information_scope="active_asset",
                    domain="identity_context",
                    entity_type="asset",
                    entity_id="BTC",
                    asset="BTC",
                    source="workspace",
                    freshness="fresh",
                    confidence="high",
                    facts={"symbol": "BTC", "asset_class": "crypto"},
                )
            ],
        ),
        (
            "read_indicator_configuration",
            "indicator_configuration",
            "Welke indicatoren staan voor BTC ingesteld?",
            [
                ReasoningEvidenceItem(
                    evidence_id="Econfig",
                    artifact_id="artifact-indicators",
                    tool_name="read_indicator_configuration",
                    information_scope="indicator_configuration",
                    domain="market_context",
                    entity_type="indicator_configuration",
                    asset="BTC",
                    source="user_indicator_rule_overrides",
                    freshness="fresh",
                    confidence="high",
                    facts={
                        "symbol": "BTC",
                        "configured_count": 3,
                        "configured_indicators": [
                            {"category": "market", "indicator": "volume"},
                            {"category": "technical", "indicator": "rsi"},
                            {"category": "technical", "indicator": "ma_200"},
                        ],
                    },
                )
            ],
        ),
    ],
)
def test_registry_read_contracts_carry_required_evidence_into_verifier(
    operation_id, required_scope, message, evidence
):
    context = _context(
        operation_id=operation_id,
        required_scope=required_scope,
        message=message,
        evidence=evidence,
    )
    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id,
        user_id=context.user_id,
        context=context,
        model="deterministic",
        error_codes=[],
    )
    draft = ResponseDraft(
        draft_id="draft-read-contract",
        run_id=context.run_id,
        user_id=context.user_id,
        mode=reasoning.mode,
        direct_answer=reasoning.direct_answer,
        main_observation=reasoning.main_observation,
        claims=reasoning.claims,
        uncertainty_summary=reasoning.uncertainty_summary,
        uncertainty_codes=reasoning.uncertainty_codes,
        evidence_refs_used=reasoning.evidence_refs_used,
        evidence_set_hash=context.evidence_set_hash,
        created_at=datetime.now(timezone.utc),
    )
    verifier = FinnV2ResponseVerifierService(session=object())._deterministic_verify(
        run=SimpleNamespace(id=context.run_id, user_id=context.user_id, message=message, conversation_id="conversation-read-contract"),
        orchestrator_result=SimpleNamespace(
            analysis=SimpleNamespace(
                subject_scopes=[required_scope],
                request_plan=RequestPlan(
                    interaction_mode="READ",
                    required_information_scopes=[required_scope],
                    operation_id=operation_id,
                ),
            ),
            selected_clarification=None,
        ),
        policy=SimpleNamespace(allowed=True, proposal_allowed=False, confirmation_required=False, operation_type=None),
        context=SimpleNamespace(evidence=evidence, uncertainty_codes=[]),
        validation=SimpleNamespace(id="validation-read-contract", evidence_set_hash=context.evidence_set_hash, integrity_status="valid"),
        draft=draft,
        repair_attempt=0,
        force_action="deliver",
    )

    assert reasoning.evidence_refs_used
    assert reasoning.claims
    assert verifier.coverage.coverage_ok is True
    assert verifier.passed is True


def test_linked_bot_read_preserves_the_complete_registry_graph_for_delivery():
    required_scopes = ["active_asset", "active_setup", "linked_strategy", "linked_bot", "bot_status"]
    evidence = [
        ReasoningEvidenceItem(evidence_id="Easset", artifact_id="asset", tool_name="read_active_asset", information_scope="active_asset", domain="identity_context", entity_type="asset", entity_id="BTC", asset="BTC", source="workspace", freshness="fresh", confidence="high", facts={"symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Esetup", artifact_id="setup", tool_name="read_active_setup", information_scope="active_setup", domain="plan_context", entity_type="setup", entity_id="309", asset="BTC", source="setups", freshness="fresh", confidence="high", facts={"setup_id": 309, "name": "BTC swing", "timeframe": "4H", "symbol": "BTC"}),
        ReasoningEvidenceItem(evidence_id="Estrat", artifact_id="strategy", tool_name="read_linked_strategy", information_scope="linked_strategy", domain="plan_context", entity_type="strategy", entity_id="325", asset="BTC", source="strategies", freshness="fresh", confidence="high", facts={"strategy_id": 325, "setup_id": 309}),
        ReasoningEvidenceItem(evidence_id="Ebot", artifact_id="bot", tool_name="read_linked_bot", information_scope="linked_bot", domain="automation_context", entity_type="bot", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "strategy_id": 325}),
        ReasoningEvidenceItem(evidence_id="Estatus", artifact_id="status", tool_name="read_bot_status", information_scope="bot_status", domain="automation_context", entity_type="bot_status", entity_id="186", asset="BTC", source="bot_configs", freshness="fresh", confidence="high", facts={"bot_id": 186, "is_live": False}),
    ]
    context = _context(
        operation_id="read_linked_bot",
        required_scope=required_scopes,
        message="Welke setup, strategie en bot heb ik voor mijn actieve asset?",
        evidence=evidence,
    )
    reasoning = FinnV2ReasoningFallbackService().grounded_read_draft(
        run_id=context.run_id, user_id=context.user_id, context=context, model="deterministic", error_codes=[]
    )
    assert reasoning.mode == "READ"
    assert {"Easset", "Esetup", "Estrat", "Ebot", "Estatus"}.issubset(reasoning.evidence_refs_used)
    assert "strategie 325" in reasoning.direct_answer
    assert "bot 186" in reasoning.direct_answer
