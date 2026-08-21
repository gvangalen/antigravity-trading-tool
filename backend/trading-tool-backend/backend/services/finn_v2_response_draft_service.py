from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.schemas.finn_v2_reasoning_schema import PersistedReasoningRecord
from backend.schemas.finn_v2_response_schema import ResponseClaim, ResponseDraft


class FinnV2ResponseDraftService:
    def build(self, *, reasoning_record: PersistedReasoningRecord) -> ResponseDraft:
        if reasoning_record.result is None:
            raise ValueError("reasoning_result_missing")
        result = reasoning_record.result
        return ResponseDraft(
            draft_id=f"finn-v2-draft-{uuid.uuid4().hex}",
            run_id=result.run_id,
            user_id=result.user_id,
            mode=result.mode,
            direct_answer=result.direct_answer,
            main_observation=result.main_observation,
            supporting_points=list(result.supporting_points),
            claims=[ResponseClaim.parse_obj(claim.dict()) for claim in result.claims],
            evidence_refs_used=list(result.evidence_refs_used),
            uncertainty_summary=result.uncertainty_summary,
            uncertainty_codes=list(result.uncertainty_codes),
            next_step=result.next_step,
            follow_up_question=result.follow_up_question,
            proposal_candidate=result.proposal_candidate,
            reasoning_result_id=reasoning_record.reasoning_result_id,
            reasoning_provenance=dict(result.reasoning_provenance),
            evidence_set_hash=reasoning_record.evidence_set_hash,
            created_at=datetime.now(timezone.utc),
        )

    def sanitize_for_semantic_verifier(self, draft: ResponseDraft) -> Dict[str, Any]:
        return {
            "mode": draft.mode,
            "direct_answer": draft.direct_answer,
            "main_observation": draft.main_observation,
            "supporting_points": [point.dict() for point in draft.supporting_points],
            "claims": [claim.dict() for claim in draft.claims],
            "evidence_refs_used": list(draft.evidence_refs_used),
            "uncertainty_summary": draft.uncertainty_summary,
            "uncertainty_codes": list(draft.uncertainty_codes),
            "next_step": draft.next_step.dict() if draft.next_step else None,
            "follow_up_question": draft.follow_up_question,
            "proposal_candidate": draft.proposal_candidate.dict() if draft.proposal_candidate else None,
        }

    def compact_evidence(self, evidence: List[Any], allowed_refs: set[str]) -> list[dict]:
        items = []
        for item in evidence:
            if item.evidence_id not in allowed_refs:
                continue
            items.append(
                {
                    "evidence_id": item.evidence_id,
                    "tool_name": item.tool_name,
                    "domain": item.domain,
                    "entity_type": item.entity_type,
                    "entity_id": item.entity_id,
                    "asset": item.asset,
                    "freshness": item.freshness,
                    "confidence": item.confidence,
                    "facts": item.facts,
                }
            )
        return items
