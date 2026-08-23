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
    return ReasoningContextPackage(
        run_id="run-read-contract",
        user_id=406,
        user_message=message,
        locale="nl-NL",
        interaction_mode="READ",
        subject_scopes=[required_scope],
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
            "required_information_scopes": [required_scope],
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
