from __future__ import annotations

from backend.schemas.finn_v2_eval_schema import GoldenCase
from backend.schemas.finn_v2_response_schema import VerifiedResponse


class CoverageGrader:
    def grade(self, *, case: GoldenCase, response: VerifiedResponse) -> tuple[float, dict[str, bool], list[str]]:
        text = f"{response.direct_answer} {response.main_observation} " + " ".join(point.title for point in response.supporting_points)
        text = text.lower()
        topics = [topic.lower() for topic in case.required_claim_topics if topic]
        covered = all(topic in text for topic in topics) if topics else True
        reasons = [] if covered else ["response_scope_incomplete"]
        return (100.0 if covered else 0.0), {"context_coverage": covered}, reasons

