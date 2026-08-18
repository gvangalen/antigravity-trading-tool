from datetime import datetime, timezone

from backend.schemas.finn_v2_domain_validation_schema import DomainValidationResult, EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_orchestrator_outcome_service import FinnV2OrchestratorOutcomeService
from backend.services.finn_v2_policy_engine_service import FinnV2PolicyEngineService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def _context(message: str, mode: str | None = None):
    analysis = FinnV2RequestAnalysisService().analyze(message=message)
    if mode is not None:
        analysis.interaction_mode = mode
    requirements = FinnV2DomainRequirementService().determine(analysis)
    plan = FinnV2ToolPlanService().build(run_id="run-1", analysis=analysis, domain_plan=requirements)
    orchestrator = OrchestratorResult(
        orchestrator_result_id="orchestrator-1",
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
        evidence_set_hash="hash-1",
        assembled_at=datetime.now(timezone.utc),
    )
    validation = EvidenceValidationResult(
        validation_id="validation-1",
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash-1",
        integrity_status="valid",
        domains=[
            DomainValidationResult(domain=domain, status="available", confidence="high")
            for domain in requirements.required_domains
        ],
        issues=[],
        validated_at=datetime.now(timezone.utc),
    )
    return orchestrator, snapshot, validation


async def _evaluate(message: str, mode: str | None = None, requested_operation: str | None = None):
    orchestrator, snapshot, validation = _context(message, mode)
    service = FinnV2PolicyEngineService(session=object())
    return await service.evaluate_run(
        user_id=7,
        run_id="run-1",
        orchestrator_result=orchestrator,
        snapshot=snapshot,
        validation=validation,
        requested_operation=requested_operation,
    )


def test_policy_mapping_for_fact_evaluation_proposal_and_actions():
    import asyncio

    fact = asyncio.run(_evaluate("Welke setup gebruik ik voor BTC?"))
    capability = asyncio.run(_evaluate("Hoi FINN, wat kun je voor mij doen?", "CAPABILITY"))
    unavailable = asyncio.run(_evaluate("Wat is nu de beste trade voor mij zonder verdere context?", "UNAVAILABLE"))
    evaluation = asyncio.run(_evaluate("Past mijn huidige BTC-strategie bij mijn risicoprofiel?", "EVALUATION"))
    proposal = asyncio.run(_evaluate("Voeg DXY toe.", "PROPOSAL"))
    paper = asyncio.run(_evaluate("Activeer mijn paper bot.", "ACTION", "activate_paper_bot"))
    live = asyncio.run(_evaluate("Zet mijn bot live.", "ACTION", "activate_live_bot"))
    unsupported = asyncio.run(_evaluate("Doe iets met mijn bot.", "ACTION"))

    assert isinstance(fact, FinnV2PolicyDecision)
    assert fact.policy_class == "read"
    assert capability.policy_class == "read"
    assert capability.allowed is True
    assert capability.reasons == ["capability_registry_read_only"]
    assert unavailable.policy_class == "read"
    assert unavailable.allowed is False
    assert evaluation.policy_class == "advice"
    assert proposal.policy_class == "proposal"
    assert proposal.proposal_input_required is True
    assert paper.policy_class == "paper_action"
    assert live.policy_class == "high_risk_action"
    assert unsupported.policy_class == "unsupported_action"


def test_policy_allows_deterministic_unavailable_delivery_when_outcome_is_unavailable():
    import asyncio

    orchestrator, snapshot, validation = _context("Wat is nu de beste trade voor mij zonder verdere context?", "UNAVAILABLE")
    orchestrator.outcome = "unavailable"
    service = FinnV2PolicyEngineService(session=object())

    decision = asyncio.run(
        service.evaluate_run(
            user_id=7,
            run_id="run-1",
            orchestrator_result=orchestrator,
            snapshot=snapshot,
            validation=validation,
        )
    )

    assert decision.policy_class == "read"
    assert decision.allowed is True
    assert decision.blocking_codes == []
    assert decision.reasons == ["deterministic_unavailable_delivery"]
