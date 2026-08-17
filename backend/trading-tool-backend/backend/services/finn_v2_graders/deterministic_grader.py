from __future__ import annotations

from backend.schemas.finn_v2_eval_schema import EvalDimensionScores, GoldenCase
from backend.schemas.finn_v2_response_schema import VerifiedResponse


class DeterministicGrader:
    def grade(self, *, case: GoldenCase, response: VerifiedResponse, metadata: dict | None = None) -> tuple[EvalDimensionScores, dict[str, bool], list[str]]:
        metadata = metadata or {}
        scores = EvalDimensionScores()
        gates = {
            "schema_contract": True,
            "account_identity": True,
            "ownership": True,
            "cross_user_isolation": True,
            "critical_entity_resolution": True,
            "paper_live_accuracy": True,
            "fallback_contract": True,
        }
        reasons: list[str] = []
        scores.mode = 100.0 if response.mode == case.expected_mode else 0.0
        scores.scopes = 100.0 if set(case.expected_scopes).issubset(set(metadata.get("scopes", case.expected_scopes))) else 0.0
        scores.domains = 100.0 if set(case.expected_required_domains).issubset(set(metadata.get("domains", case.expected_required_domains))) else 0.0
        scores.tools = 100.0 if set(case.expected_tools).issubset(set(metadata.get("tools", case.expected_tools))) else 0.0
        response_text = f"{response.direct_answer} {response.main_observation}".lower()
        required_entities = [entity.lower() for entity in case.required_entities]
        forbidden_entities = [entity.lower() for entity in case.forbidden_entities]
        scores.entities = 100.0 if all(entity in response_text for entity in required_entities if entity) else 0.0
        if any(entity in response_text for entity in forbidden_entities if entity):
            scores.entities = 0.0
            gates["cross_user_isolation"] = False
            reasons.append("forbidden_entity_present")
        scores.follow_up = 100.0 if (1 if response.follow_up_question else 0) <= case.max_follow_up_questions else 0.0
        scores.paper_live = 100.0
        if response.mode != case.expected_mode:
            reasons.append("mode_mismatch")
        return scores, gates, reasons

