from datetime import datetime, timezone

from backend.schemas.finn_v2_domain_validation_schema import (
    ClarificationCandidate,
    DomainValidationResult,
    EvidenceIssue,
    EvidenceValidationResult,
)
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_orchestrator_outcome_service import FinnV2OrchestratorOutcomeService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def _build_inputs(message: str):
    analysis = FinnV2RequestAnalysisService().analyze(message=message)
    domain_requirements = FinnV2DomainRequirementService().determine(analysis)
    tool_plan = FinnV2ToolPlanService().build(run_id="run-1", analysis=analysis, domain_plan=domain_requirements)
    return analysis, domain_requirements, tool_plan


def test_orchestrator_outcome_is_reasoning_ready_for_degraded_non_blocking_domains():
    analysis, domain_requirements, tool_plan = _build_inputs("Staat mijn gekoppelde bot live?")
    validation = EvidenceValidationResult(
        validation_id="validation-1",
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash",
        integrity_status="degraded",
        domains=[
            DomainValidationResult(
                domain="identity_context",
                status="available",
                confidence="high",
            ),
            DomainValidationResult(
                domain="automation_context",
                status="degraded",
                confidence="medium",
                issues=[EvidenceIssue(code="evidence_freshness_stale:read_bot_status", severity="warning", domain="automation_context", message="stale")],
            ),
            DomainValidationResult(
                domain="plan_context",
                status="available",
                confidence="high",
            ),
        ],
        issues=[],
        validated_at=datetime.now(timezone.utc),
    )

    result = FinnV2OrchestratorOutcomeService().evaluate(
        run_id="run-1",
        user_id=7,
        analysis=analysis,
        domain_requirements=domain_requirements,
        tool_plan=tool_plan,
        snapshot_id="snapshot-1",
        validation=validation,
    )

    assert result.outcome == "reasoning_ready"
    assert result.uncertainty_codes == ["evidence_freshness_stale:read_bot_status"]


def test_orchestrator_outcome_picks_single_clarification_candidate_by_priority():
    analysis, domain_requirements, tool_plan = _build_inputs("Welke bot is aan deze strategie gekoppeld?")
    validation = EvidenceValidationResult(
        validation_id="validation-2",
        snapshot_id="snapshot-2",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash",
        integrity_status="valid",
        domains=[
            DomainValidationResult(
                domain="identity_context",
                status="available",
                confidence="high",
            ),
            DomainValidationResult(
                domain="plan_context",
                status="available",
                confidence="high",
            ),
            DomainValidationResult(
                domain="automation_context",
                status="ambiguous",
                confidence="low",
                clarification_candidates=[
                    ClarificationCandidate(
                        code="ambiguous_bot",
                        domain="automation_context",
                        question="Welke bot bedoel je precies?",
                        entity_type="bot",
                    )
                ],
            ),
        ],
        issues=[],
        validated_at=datetime.now(timezone.utc),
    )

    result = FinnV2OrchestratorOutcomeService().evaluate(
        run_id="run-1",
        user_id=7,
        analysis=analysis,
        domain_requirements=domain_requirements,
        tool_plan=tool_plan,
        snapshot_id="snapshot-2",
        validation=validation,
    )

    assert result.outcome == "clarification_required"
    assert result.selected_clarification is not None
    assert result.selected_clarification.entity_type == "bot"


def test_orchestrator_outcome_marks_required_invalid_domain_unavailable():
    analysis, domain_requirements, tool_plan = _build_inputs("Welke setup gebruik ik voor BTC?")
    validation = EvidenceValidationResult(
        validation_id="validation-3",
        snapshot_id="snapshot-3",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash",
        integrity_status="invalid",
        domains=[
            DomainValidationResult(
                domain="plan_context",
                status="invalid",
                confidence="none",
                issues=[EvidenceIssue(code="conflict_asset_setup", severity="blocking", domain="plan_context", message="invalid")],
            ),
        ],
        issues=[EvidenceIssue(code="conflict_asset_setup", severity="blocking", domain="plan_context", message="invalid")],
        validated_at=datetime.now(timezone.utc),
    )

    result = FinnV2OrchestratorOutcomeService().evaluate(
        run_id="run-1",
        user_id=7,
        analysis=analysis,
        domain_requirements=domain_requirements,
        tool_plan=tool_plan,
        snapshot_id="snapshot-3",
        validation=validation,
    )

    assert result.outcome == "unavailable"
    assert "conflict_asset_setup" in result.unavailable_codes
