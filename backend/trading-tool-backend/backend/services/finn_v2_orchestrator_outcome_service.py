from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.schemas.finn_v2_domain_validation_schema import ClarificationCandidate, EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import (
    CLARIFICATION_PRIORITY,
    DomainRequirementPlan,
    ORCHESTRATOR_VERSION,
    OrchestratorResult,
    RequestAnalysisResult,
    ToolPlan,
)


class FinnV2OrchestratorOutcomeService:
    def build_failed_result(
        self,
        *,
        run_id: str,
        user_id: int,
        analysis: RequestAnalysisResult,
        domain_requirements: DomainRequirementPlan,
        tool_plan: ToolPlan,
        unavailable_codes: list[str],
    ) -> OrchestratorResult:
        return OrchestratorResult(
            orchestrator_result_id=f"finn-v2-orchestrator-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            analysis=analysis,
            domain_requirements=domain_requirements,
            tool_plan=tool_plan,
            outcome="failed",
            unavailable_codes=unavailable_codes,
            orchestrator_version=ORCHESTRATOR_VERSION,
            created_at=datetime.now(timezone.utc),
        )

    def evaluate(
        self,
        *,
        run_id: str,
        user_id: int,
        analysis: RequestAnalysisResult,
        domain_requirements: DomainRequirementPlan,
        tool_plan: ToolPlan,
        snapshot_id: Optional[str],
        validation: Optional[EvidenceValidationResult],
    ) -> OrchestratorResult:
        if snapshot_id is None or validation is None:
            return self.build_failed_result(
                run_id=run_id,
                user_id=user_id,
                analysis=analysis,
                domain_requirements=domain_requirements,
                tool_plan=tool_plan,
                unavailable_codes=["orchestrator_missing_validation"],
            )

        domain_map = {item.domain: item for item in validation.domains}
        unavailable_codes: list[str] = []
        uncertainty_codes: list[str] = []
        clarification_candidates: list[ClarificationCandidate] = []

        if validation.integrity_status == "invalid":
            unavailable_codes.extend(issue.code for issue in validation.issues)

        for domain in domain_requirements.required_domains:
            result = domain_map.get(domain)
            if result is None:
                unavailable_codes.append("required_domain_missing")
                continue
            if result.status == "not_collected":
                return self.build_failed_result(
                    run_id=run_id,
                    user_id=user_id,
                    analysis=analysis,
                    domain_requirements=domain_requirements,
                    tool_plan=tool_plan,
                    unavailable_codes=["required_domain_not_collected"],
                )
            if result.status == "invalid":
                unavailable_codes.extend(issue.code for issue in result.issues)
            elif result.status == "ambiguous":
                clarification_candidates.extend(result.clarification_candidates)
                clarification_candidates.extend(self._missing_entity_clarifications(result.issues, domain))
            elif result.status == "unavailable":
                clarification_candidates.extend(self._missing_entity_clarifications(result.issues, domain))
                if not clarification_candidates:
                    unavailable_codes.extend(issue.code for issue in result.issues or [])
            elif result.status == "degraded":
                uncertainty_codes.extend(issue.code for issue in result.issues)

        outcome = "reasoning_ready"
        selected_clarification = self._select_clarification(clarification_candidates)
        if unavailable_codes:
            outcome = "unavailable"
        elif selected_clarification is not None:
            outcome = "clarification_required"

        return OrchestratorResult(
            orchestrator_result_id=f"finn-v2-orchestrator-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            analysis=analysis,
            domain_requirements=domain_requirements,
            tool_plan=tool_plan,
            snapshot_id=snapshot_id,
            validation_id=validation.validation_id,
            outcome=outcome,
            selected_clarification=selected_clarification,
            unavailable_codes=unavailable_codes,
            uncertainty_codes=uncertainty_codes,
            orchestrator_version=ORCHESTRATOR_VERSION,
            created_at=datetime.now(timezone.utc),
        )

    def _missing_entity_clarifications(self, issues, domain: str) -> list[ClarificationCandidate]:
        candidates = []
        mapping = {
            "asset_not_resolved": ("missing_asset", "Over welke asset wil je dat ik dit bekijk?", "asset"),
            "setup_not_resolved": ("missing_setup", "Welke setup bedoel je precies?", "setup"),
            "strategy_not_resolved": ("missing_strategy", "Welke strategie bedoel je precies?", "strategy"),
            "bot_not_resolved": ("missing_bot", "Welke bot bedoel je precies?", "bot"),
        }
        for issue in issues:
            if issue.code not in mapping:
                continue
            code, question, entity_type = mapping[issue.code]
            candidates.append(
                ClarificationCandidate(
                    code=code,
                    domain=domain,
                    question=question,
                    entity_type=entity_type,
                )
            )
        return candidates

    def _select_clarification(self, candidates: list[ClarificationCandidate]) -> Optional[ClarificationCandidate]:
        if not candidates:
            return None
        for entity_type in CLARIFICATION_PRIORITY:
            for candidate in candidates:
                if candidate.entity_type == entity_type:
                    return candidate
        return candidates[0]
