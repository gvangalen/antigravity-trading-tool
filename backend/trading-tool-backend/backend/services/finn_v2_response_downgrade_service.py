from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.schemas.finn_v2_response_schema import ResponseDraft


class FinnV2ResponseDowngradeService:
    def downgrade_to_fact(self, *, draft: ResponseDraft) -> ResponseDraft:
        claims = [claim for claim in draft.claims if claim.claim_type in {"fact", "uncertainty"} and claim.evidence_refs]
        supporting_points = [point for point in draft.supporting_points if point.evidence_refs][:4]
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="FACT",
            direct_answer=draft.direct_answer,
            main_observation=draft.main_observation,
            supporting_points=supporting_points,
            claims=claims,
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=draft.uncertainty_summary,
            uncertainty_codes=list(draft.uncertainty_codes),
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def downgrade_to_clarification(self, *, draft: ResponseDraft, orchestrator_result: OrchestratorResult) -> ResponseDraft:
        question = draft.follow_up_question or (
            orchestrator_result.selected_clarification.question if orchestrator_result.selected_clarification else "Welke keuze wil je dat ik beoordeel?"
        )
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="CLARIFICATION",
            direct_answer="Ik mis nog een noodzakelijke keuze om dit veilig en precies te beantwoorden.",
            main_observation="De huidige context laat meerdere geldige interpretaties toe.",
            supporting_points=[],
            claims=[],
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=None,
            uncertainty_codes=[],
            next_step=None,
            follow_up_question=question,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def downgrade_to_unavailable(self, *, draft: ResponseDraft, reason: Optional[str]) -> ResponseDraft:
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=draft.run_id,
            user_id=draft.user_id,
            mode="UNAVAILABLE",
            direct_answer="Ik kan hier nu geen veilig onderbouwd antwoord op uitleveren.",
            main_observation=str(reason or "De benodigde verificatie voor deze response is niet geslaagd."),
            supporting_points=[],
            claims=[],
            evidence_refs_used=list(draft.evidence_refs_used),
            uncertainty_summary=str(reason or "De context is onvoldoende veilig of volledig voor levering."),
            uncertainty_codes=[],
            next_step=None,
            follow_up_question=None,
            proposal_candidate=None,
            reasoning_result_id=draft.reasoning_result_id,
            evidence_set_hash=draft.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )
