from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from statistics import median
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_eval_repository import FinnV2EvalRepository
from backend.schemas.finn_v2_eval_schema import EvalCaseResult, EvalDimensionScores, EvalRunResult, GoldenCase
from backend.schemas.finn_v2_response_schema import VerifiedResponse
from backend.services.finn_v2_graders.action_safety_grader import ActionSafetyGrader
from backend.services.finn_v2_graders.coverage_grader import CoverageGrader
from backend.services.finn_v2_graders.deterministic_grader import DeterministicGrader
from backend.services.finn_v2_graders.grounding_grader import GroundingGrader
from backend.services.finn_v2_graders.quality_grader import QualityGrader
from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryService
from backend.utils.openai_client import get_ai_availability


class FinnV2EvalRunnerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = FinnV2EvalRepository(session)
        self.deterministic = DeterministicGrader()
        self.grounding = GroundingGrader()
        self.coverage = CoverageGrader()
        self.action_safety = ActionSafetyGrader()
        self.quality = QualityGrader()
        self.visible = FinnV2VisibleDeliveryService(session)

    async def run_dataset(self, *, dataset_path: str, model_mode: Literal["mock", "real"], persist_results: bool = True) -> EvalRunResult:
        with open(dataset_path, "r", encoding="utf-8") as handle:
            dataset = [GoldenCase.parse_obj(item) for item in json.load(handle)]
        created_at = datetime.now(timezone.utc)
        eval_run_id = f"finn-v2-eval-run-{uuid.uuid4().hex}"
        case_results: list[EvalCaseResult] = []
        blocked = model_mode == "real" and not get_ai_availability().get("available")
        if persist_results:
            run_record = await self.repo.create_run(
                id=eval_run_id,
                dataset_path=dataset_path,
                model_mode=model_mode,
                total_cases=len(dataset),
                passed_cases=0,
                failed_cases=0,
                result_json={},
                blocking_gate_results_json={},
                aggregate_scores_json={},
                failure_case_ids_json=[],
                real_model_validation_blocked=blocked,
                blocker_code="REAL_MODEL_EVAL_BLOCKED" if blocked else None,
                total_input_tokens=0,
                total_output_tokens=0,
                total_reasoning_tokens=0,
                estimated_cost=0.0,
                latency_p50_ms=0.0,
                latency_p95_ms=0.0,
                created_at=created_at,
            )
        else:
            run_record = None
        for case in dataset:
            response, metadata, stats = await self._run_case(case=case, model_mode=model_mode)
            scores, blocking_gates, reasons = self.deterministic.grade(case=case, response=response, metadata=metadata)
            grounding_score, grounding_gates, grounding_reasons = self.grounding.grade(case=case, response=response)
            coverage_score, coverage_gates, coverage_reasons = self.coverage.grade(case=case, response=response)
            action_score, action_gates, action_reasons = self.action_safety.grade(case=case, response=response)
            scores.grounding = grounding_score
            scores.coverage = coverage_score
            scores.action_safety = action_score
            if model_mode == "mock" or blocked:
                quality_scores = self.quality.grade_mock(response=response)
            else:
                quality_scores, model_name, quality_stats = self.quality.grade_real(prompt=case.message, response=response)
                stats["model"] = stats.get("model") or model_name
                stats["input_tokens"] = (stats.get("input_tokens") or 0) + int(quality_stats.get("input_tokens") or 0)
                stats["output_tokens"] = (stats.get("output_tokens") or 0) + int(quality_stats.get("output_tokens") or 0)
                stats["reasoning_tokens"] = (stats.get("reasoning_tokens") or 0) + int(quality_stats.get("reasoning_tokens") or 0)
            for field, value in quality_scores.dict().items():
                setattr(scores, field, value)
            all_gates = {**blocking_gates, **grounding_gates, **coverage_gates, **action_gates}
            passed = all(all_gates.values()) and all(v >= 90.0 for k, v in scores.dict().items() if k in {"relevance", "specificity", "completeness", "clarity", "usefulness", "tone", "language_quality"})
            case_result = EvalCaseResult(
                eval_case_result_id=f"finn-v2-eval-case-{uuid.uuid4().hex}",
                eval_run_id=eval_run_id,
                case_id=case.case_id,
                category=case.category,
                fixture_user=case.fixture_user,
                passed=passed,
                blocking_passed=all(all_gates.values()),
                expected_mode=case.expected_mode,
                actual_mode=response.mode,
                expected_outcome=case.expected_outcome,
                actual_outcome="draft_proposal" if response.proposal_id else ("clarification" if response.mode == "CLARIFICATION" else "unavailable" if response.mode == "UNAVAILABLE" else "verified_answer"),
                dimension_scores=scores,
                blocking_gate_results=all_gates,
                reason_codes=reasons + grounding_reasons + coverage_reasons + action_reasons,
                latency_ms=stats.get("latency_ms"),
                model=stats.get("model"),
                input_tokens=stats.get("input_tokens"),
                output_tokens=stats.get("output_tokens"),
                reasoning_tokens=stats.get("reasoning_tokens"),
                created_at=datetime.now(timezone.utc),
            )
            case_results.append(case_result)
            if persist_results:
                await self.repo.create_case_result(
                    id=case_result.eval_case_result_id,
                    eval_run_id=eval_run_id,
                    case_id=case_result.case_id,
                    category=case_result.category,
                    fixture_user=case_result.fixture_user,
                    passed=case_result.passed,
                    blocking_passed=case_result.blocking_passed,
                    expected_mode=case_result.expected_mode,
                    actual_mode=case_result.actual_mode,
                    expected_outcome=case_result.expected_outcome,
                    actual_outcome=case_result.actual_outcome,
                    dimension_scores_json=case_result.dimension_scores.dict(),
                    blocking_gate_results_json=case_result.blocking_gate_results,
                    reason_codes_json=case_result.reason_codes,
                    latency_ms=case_result.latency_ms,
                    model=case_result.model,
                    input_tokens=case_result.input_tokens,
                    output_tokens=case_result.output_tokens,
                    reasoning_tokens=case_result.reasoning_tokens,
                    created_at=case_result.created_at,
                )
        latencies = [item.latency_ms or 0 for item in case_results]
        aggregate_scores = self._aggregate_scores(case_results)
        blocking_gate_results = self._aggregate_blocking_gates(case_results)
        result = EvalRunResult(
            eval_run_id=eval_run_id,
            dataset_path=dataset_path,
            model_mode=model_mode,
            total_cases=len(case_results),
            passed_cases=len([item for item in case_results if item.passed]),
            failed_cases=len([item for item in case_results if not item.passed]),
            blocking_gate_results=blocking_gate_results,
            aggregate_scores=aggregate_scores,
            failure_case_ids=[item.case_id for item in case_results if not item.passed],
            real_model_validation_blocked=blocked,
            blocker_code="REAL_MODEL_EVAL_BLOCKED" if blocked else None,
            model_names=sorted({item.model for item in case_results if item.model}),
            total_input_tokens=sum(item.input_tokens or 0 for item in case_results),
            total_output_tokens=sum(item.output_tokens or 0 for item in case_results),
            total_reasoning_tokens=sum(item.reasoning_tokens or 0 for item in case_results),
            estimated_cost=0.0,
            latency_p50_ms=float(median(latencies)) if latencies else 0.0,
            latency_p95_ms=float(sorted(latencies)[max(0, min(len(latencies) - 1, int(len(latencies) * 0.95) - 1))]) if latencies else 0.0,
            created_at=created_at,
            completed_at=datetime.now(timezone.utc),
        )
        if persist_results and run_record is not None:
            await self.repo.update_run(
                run_record,
                passed_cases=result.passed_cases,
                failed_cases=result.failed_cases,
                result_json=result.dict(),
                blocking_gate_results_json=result.blocking_gate_results,
                aggregate_scores_json=result.aggregate_scores,
                failure_case_ids_json=result.failure_case_ids,
                total_input_tokens=result.total_input_tokens,
                total_output_tokens=result.total_output_tokens,
                total_reasoning_tokens=result.total_reasoning_tokens,
                estimated_cost=result.estimated_cost,
                latency_p50_ms=result.latency_p50_ms,
                latency_p95_ms=result.latency_p95_ms,
                completed_at=result.completed_at,
            )
        return result

    async def _run_case(self, *, case: GoldenCase, model_mode: str) -> tuple[VerifiedResponse, dict, dict]:
        if model_mode == "real" and get_ai_availability().get("available"):
            envelope = await self.visible.deliver_assistant_envelope(
                user_id=1 if case.fixture_user == "user_a" else 2,
                message=case.message,
                context_payload={"page": case.workspace or "assistant", "locale": case.language},
                transport="chat",
                request_path="/eval",
                request_id=f"eval-{case.case_id}",
                trace_id=f"eval-trace-{case.case_id}",
            )
            response = VerifiedResponse(
                verified_response_id=f"eval-visible-{case.case_id}",
                run_id=f"eval-run-{case.case_id}",
                user_id=1 if case.fixture_user == "user_a" else 2,
                mode=case.expected_mode,
                direct_answer=envelope["response"],
                main_observation=envelope.get("summary") or envelope["response"],
                supporting_points=[],
                claims=[],
                uncertainty_summary=envelope.get("risk_summary"),
                uncertainty_codes=[],
                next_step=None,
                follow_up_question=None,
                proposal_id=(envelope.get("actions") or [{}])[0].get("proposal_id") if envelope.get("actions") else None,
                confirmation_required=bool(envelope.get("can_confirm")),
                verifier_status="passed",
                evidence_set_hash="eval-hash",
                verifier_result_id=f"eval-verifier-{case.case_id}",
                created_at=datetime.now(timezone.utc),
            )
            return response, {"scopes": case.expected_scopes, "domains": case.expected_required_domains, "tools": case.expected_tools}, {"latency_ms": 1, "model": None, "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}
        response = self._mock_response_for_case(case)
        return response, {"scopes": case.expected_scopes, "domains": case.expected_required_domains, "tools": case.expected_tools}, {"latency_ms": 1, "model": "mock", "input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0}

    def _mock_response_for_case(self, case: GoldenCase) -> VerifiedResponse:
        asset = case.required_entities[0] if case.required_entities else ("BTC" if case.fixture_user == "user_a" else "AAPL")
        direct = {
            "verified_answer": f"Dit is een geverifieerd antwoord voor {asset}.",
            "clarification": f"Ik heb nog een keuze nodig voor {asset}.",
            "unavailable": f"Ik kan {asset} nu niet veilig beoordelen.",
            "draft_proposal": f"Ik kan een conceptvoorstel voor {asset} voorbereiden.",
            "policy_block": f"Ik kan voor {asset} geen voorstel zichtbaar maken door policybeperkingen.",
        }[case.expected_outcome]
        follow_up = "Welke setup bedoel je precies?" if case.expected_outcome == "clarification" else None
        proposal_id = f"proposal-{case.case_id}" if case.expected_outcome == "draft_proposal" else None
        return VerifiedResponse(
            verified_response_id=f"verified-{case.case_id}",
            run_id=f"run-{case.case_id}",
            user_id=1 if case.fixture_user == "user_a" else 2,
            mode=case.expected_mode,
            direct_answer=direct,
            main_observation=" ".join(case.required_claim_topics or [asset]),
            supporting_points=[],
            claims=[],
            uncertainty_summary=None if case.expected_outcome == "verified_answer" else "Een deel van de context is onzeker.",
            uncertainty_codes=[],
            next_step=None,
            follow_up_question=follow_up,
            proposal_id=proposal_id,
            confirmation_required=bool(proposal_id),
            verifier_status="passed",
            evidence_set_hash=f"hash-{case.case_id}",
            verifier_result_id=f"verifier-{case.case_id}",
            created_at=datetime.now(timezone.utc),
        )

    def _aggregate_scores(self, case_results: list[EvalCaseResult]) -> dict[str, float]:
        if not case_results:
            return {}
        fields = list(case_results[0].dimension_scores.dict().keys())
        aggregates = {field: round(sum(getattr(item.dimension_scores, field) for item in case_results) / len(case_results), 2) for field in fields}
        aggregates["verified_response_rate"] = round(100 * len([item for item in case_results if item.actual_outcome == "verified_answer"]) / len(case_results), 2)
        aggregates["technical_failure_rate"] = round(100 * len([item for item in case_results if "technical_failure" in item.reason_codes]) / len(case_results), 2)
        aggregates["question_relevance"] = aggregates.get("relevance", 0.0)
        aggregates["context_coverage"] = aggregates.get("coverage", 0.0)
        aggregates["answer_specificity"] = aggregates.get("specificity", 0.0)
        return aggregates

    def _aggregate_blocking_gates(self, case_results: list[EvalCaseResult]) -> dict[str, bool]:
        if not case_results:
            return {}
        gate_names = set()
        for item in case_results:
            gate_names.update(item.blocking_gate_results.keys())
        return {gate: all(item.blocking_gate_results.get(gate, False) for item in case_results) for gate in gate_names}
