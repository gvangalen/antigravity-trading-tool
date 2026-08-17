from __future__ import annotations

from backend.schemas.finn_v2_eval_schema import EvalDimensionScores, GoldenCase
from backend.schemas.finn_v2_response_schema import VerifiedResponse


class GroundingGrader:
    def grade(self, *, case: GoldenCase, response: VerifiedResponse) -> tuple[float, dict[str, bool], list[str]]:
        reasons: list[str] = []
        factual_claims = [claim for claim in response.claims if claim.claim_type in {"fact", "inference", "evaluation"}]
        if not factual_claims:
            return 100.0, {"claim_grounding": True}, reasons
        grounded = all(bool(claim.evidence_refs) for claim in factual_claims)
        if not grounded:
            reasons.append("ungrounded_claim")
        forbidden = [value.lower() for value in case.forbidden_claims]
        response_text = f"{response.direct_answer} {response.main_observation}".lower()
        if any(text in response_text for text in forbidden if text):
            grounded = False
            reasons.append("forbidden_claim_present")
        return (100.0 if grounded else 0.0), {"claim_grounding": grounded}, reasons

