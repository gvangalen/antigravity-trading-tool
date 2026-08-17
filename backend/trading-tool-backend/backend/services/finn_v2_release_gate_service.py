from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_eval_repository import FinnV2EvalRepository
from backend.infrastructure.repositories.finn_v2_release_gate_repository import FinnV2ReleaseGateRepository
from backend.schemas.finn_v2_cutover_schema import FinnV2ReleaseGateResult


BLOCKING_GATES = [
    "schema_contract",
    "account_identity",
    "ownership",
    "cross_user_isolation",
    "critical_entity_resolution",
    "claim_grounding",
    "action_safety",
    "paper_live_accuracy",
    "a1_a3_b1_b4",
    "fallback_contract",
    "prompt_injection_safety",
]


class FinnV2ReleaseGateService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.eval_repo = FinnV2EvalRepository(session)
        self.repo = FinnV2ReleaseGateRepository(session)

    async def evaluate(self, *, eval_run) -> FinnV2ReleaseGateResult:
        blocking = {gate: bool(eval_run.blocking_gate_results.get(gate, False)) for gate in BLOCKING_GATES}
        quality = dict(eval_run.aggregate_scores)
        operational = {
            "verified_response_rate": float(eval_run.aggregate_scores.get("verified_response_rate", 100.0)),
            "technical_failure_rate": float(eval_run.aggregate_scores.get("technical_failure_rate", 0.0)),
            "p95_latency_ms": float(eval_run.latency_p95_ms or 0.0),
            "no_indefinite_pending": True,
            "real_model_validation_blocked": bool(getattr(eval_run, "real_model_validation_blocked", False)),
        }
        reason_codes = [gate for gate, passed in blocking.items() if not passed]
        if quality.get("question_relevance", 100.0) < 95.0:
            reason_codes.append("question_relevance")
        if quality.get("context_coverage", 100.0) < 95.0:
            reason_codes.append("context_coverage")
        if operational["real_model_validation_blocked"]:
            reason_codes.append(getattr(eval_run, "blocker_code", None) or "REAL_MODEL_EVAL_BLOCKED")
        passed = not reason_codes
        result = FinnV2ReleaseGateResult(
            release_gate_result_id=f"finn-v2-release-gate-{uuid.uuid4().hex}",
            eval_run_id=eval_run.eval_run_id,
            passed=passed,
            blocking_gates=blocking,
            quality_gates=quality,
            operational_gates=operational,
            reason_codes=reason_codes,
            created_at=datetime.now(timezone.utc),
        )
        await self.repo.create(
            id=result.release_gate_result_id,
            eval_run_id=result.eval_run_id,
            passed=result.passed,
            result_json=result.dict(),
            reason_codes_json=result.reason_codes,
            created_at=result.created_at,
        )
        return result
