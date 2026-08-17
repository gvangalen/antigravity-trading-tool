from datetime import datetime, timezone
import asyncio

from backend.schemas.finn_v2_domain_validation_schema import DomainValidationResult, EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import DomainRequirementPlan, OrchestratorResult
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot, ToolOutcome
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_policy_engine_service import FinnV2PolicyEngineService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService
from backend.services.finn_v2_tool_plan_service import FinnV2ToolPlanService


def _build(mode: str, required_domains: list[str], tool_outcomes: list[ToolOutcome], integrity: str = "valid"):
    analysis = FinnV2RequestAnalysisService().analyze(message="placeholder")
    analysis.interaction_mode = mode
    requirements = DomainRequirementPlan(required_domains=required_domains, optional_domains=[], requirement_reason=[])
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
        tool_outcomes=tool_outcomes,
        assembled_at=datetime.now(timezone.utc),
    )
    validation = EvidenceValidationResult(
        validation_id="validation-1",
        snapshot_id="snapshot-1",
        run_id="run-1",
        user_id=7,
        evidence_set_hash="hash",
        integrity_status=integrity,
        domains=[DomainValidationResult(domain=domain, status="available", confidence="high") for domain in required_domains],
        issues=[],
        validated_at=datetime.now(timezone.utc),
    )
    return orchestrator, snapshot, validation


def test_stale_market_blocks_live_activation_but_not_indicator_change():
    service = FinnV2PolicyEngineService(session=object())

    live_orch, live_snapshot, live_validation = _build(
        "ACTION",
        ["identity_context", "market_context", "plan_context", "automation_context"],
        [ToolOutcome(tool_name="read_market_snapshot", status="stale"), ToolOutcome(tool_name="read_bot_status", status="available")],
    )
    indicator_orch, indicator_snapshot, indicator_validation = _build(
        "PROPOSAL",
        ["identity_context", "market_context"],
        [ToolOutcome(tool_name="read_market_snapshot", status="stale")],
    )

    live = asyncio.run(
        service.evaluate_run(
            user_id=7,
            run_id="run-1",
            orchestrator_result=live_orch,
            snapshot=live_snapshot,
            validation=live_validation,
            requested_operation="activate_live_bot",
        )
    )
    indicator = asyncio.run(
        service.evaluate_run(
            user_id=7,
            run_id="run-1",
            orchestrator_result=indicator_orch,
            snapshot=indicator_snapshot,
            validation=indicator_validation,
        )
    )

    assert "market_snapshot_stale" in live.blocking_codes
    assert "market_snapshot_stale" not in indicator.blocking_codes
