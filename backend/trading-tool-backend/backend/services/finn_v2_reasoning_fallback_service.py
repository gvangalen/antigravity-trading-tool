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
                direct_answer="Ik kan nog geen verantwoorde trade of financiële conclusie geven met de huidige context.",
                main_observation="Er ontbreekt nog één noodzakelijke verduidelijking voordat ik dit veilig kan beoordelen.",
                uncertainty_summary="Zonder die extra context zou ik moeten gokken.",
                uncertainty_codes=orchestrator_result.unavailable_codes,
                follow_up_question=question,
                evidence_refs_used=[],
                model=model,
                created_at=datetime.now(timezone.utc),
            )
        asset = orchestrator_result.analysis.explicit_asset
        next_question = (
            f"Wil je eerst je huidige setup voor {asset} laten beoordelen?"
            if asset
            else "Wil je eerst aangeven over welke asset of setup je dit wilt bekijken?"
        )
        return ReasoningResult(
            reasoning_result_id=f"finn-v2-reasoning-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            mode="UNAVAILABLE",
            direct_answer="Ik kan nog geen verantwoorde trade aanwijzen, omdat essentiële markt- of setupcontext ontbreekt.",
            main_observation="Zonder actuele context, een geldige setup en voldoende onderbouwing zou ik een financiële conclusie verzinnen.",
            uncertainty_summary=next_question,
            uncertainty_codes=orchestrator_result.unavailable_codes or orchestrator_result.uncertainty_codes,
            follow_up_question=next_question,
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
