from datetime import datetime, timezone
import asyncio

from backend.schemas.finn_v2_domain_validation_schema import DomainValidationResult, EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import DomainRequirementPlan, OrchestratorResult
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services.finn_v2_policy_engine_service import FinnV2PolicyEngineService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def test_unavailable_review_does_not_block_setup_policy():
    analysis = FinnV2RequestAnalysisService().analyze(message="Ik wil mijn setup aanpassen.")
    analysis.interaction_mode = "PROPOSAL"
    requirements = DomainRequirementPlan(required_domains=["plan_context"], optional_domains=["review_context"], requirement_reason=[])
    plan = FinnV2ToolPlanService().build(run_id="run-1", analysis=analysis, domain_plan=requirements)
    orchestrator = OrchestratorResult(
        orchestrator_result_id="o-1",
        run_id="run-1",
        user_id=7,
        analysis=analysis,
        domain_requirements=requirements,
        tool_plan=plan,
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        outcome="reasoning_ready",
        created_at=datetime.now(timezone.utc),
    )
    snapshot = FinancialStateSnapshot(
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        revision=1,
        evidence_set_hash="hash",
        assembled_at=datetime.now(timezone.utc),
    )
    validation = EvidenceValidationResult(
        validation_id="validation-1",
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash",
        integrity_status="valid",
        domains=[
            DomainValidationResult(domain="plan_context", status="available", confidence="high"),
            DomainValidationResult(domain="review_context", status="unavailable", confidence="none"),
        ],
        issues=[],
        validated_at=datetime.now(timezone.utc),
    )

    decision = asyncio.run(
        FinnV2PolicyEngineService(session=object()).evaluate_run(
            user_id=7,
            run_id="run-1",
            orchestrator_result=orchestrator,
            snapshot=snapshot,
            validation=validation,
        )
    )

    assert decision.allowed is True
    assert "required_domain_unavailable" not in decision.blocking_codes
