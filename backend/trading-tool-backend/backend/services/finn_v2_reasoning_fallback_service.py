from __future__ import annotations

import uuid
from datetime import datetime, timezone

from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_reasoning_schema import ReasoningResult


class FinnV2ReasoningFallbackService:
    def deterministic_draft(self, *, run_id: str, user_id: int, orchestrator_result: OrchestratorResult, model: str) -> ReasoningResult:
        mode = orchestrator_result.outcome
        if mode == "clarification_required":
            question = orchestrator_result.selected_clarification.question if orchestrator_result.selected_clarification else "Welke verduidelijking heb je precies nodig?"
            return ReasoningResult(
                reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
                run_id=run_id,
                user_id=user_id,
                mode="CLARIFICATION",
                direct_answer="Er is nog een gerichte verduidelijking nodig voordat FINN V2 inhoudelijk kan redeneren.",
                main_observation="Een noodzakelijke entityselectie ontbreekt of is ambigu.",
                uncertainty_summary="De huidige context is onvoldoende eenduidig.",
                uncertainty_codes=orchestrator_result.unavailable_codes,
                follow_up_question=question,
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="UNAVAILABLE",
            direct_answer="FINN V2 kan voor deze shadowrun nog geen veilige inhoudelijke analyse opstellen.",
            main_observation="De orchestratoruitkomst is niet klaar voor modelreasoning.",
            uncertainty_summary="De beschikbare context is onvolledig of onveilig voor verdere analyse.",
            uncertainty_codes=orchestrator_result.unavailable_codes or orchestrator_result.uncertainty_codes,
            evidence_refs_used=[],
            model=model,
            created_at=datetime.now(timezone.utc),
        )

    def unavailable_draft(self, *, run_id: str, user_id: int, mode: str, error_codes: list[str], model: str) -> ReasoningResult:
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode=mode,
            direct_answer="FINN V2 reasoning is momenteel niet beschikbaar voor deze shadowrun.",
            main_observation="De centrale AI-runtime of configuratie liet geen veilige reasoningcall toe.",
            uncertainty_summary="De analyse is deterministisch afgebroken voordat een modelcall werd gedaan.",
            uncertainty_codes=error_codes,
            evidence_refs_used=[],
            model=model,
            created_at=datetime.now(timezone.utc),
        )
