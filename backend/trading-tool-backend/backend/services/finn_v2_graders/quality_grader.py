from __future__ import annotations

from typing import Optional

from backend.schemas.finn_v2_eval_schema import EvalDimensionScores
from backend.schemas.finn_v2_response_schema import VerifiedResponse
from backend.utils import openai_client


class QualityGrader:
    SCHEMA = {
        "name": "finn_v2_quality_grader",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "relevance": {"type": "number"},
                "specificity": {"type": "number"},
                "completeness": {"type": "number"},
                "clarity": {"type": "number"},
                "usefulness": {"type": "number"},
                "brevity": {"type": "number"},
                "tone": {"type": "number"},
                "uncertainty_quality": {"type": "number"},
                "next_step_quality": {"type": "number"},
                "language_quality": {"type": "number"},
            },
            "required": ["relevance", "specificity", "completeness", "clarity", "usefulness", "brevity", "tone", "uncertainty_quality", "next_step_quality", "language_quality"],
        },
    }

    def grade_mock(self, *, response: VerifiedResponse) -> EvalDimensionScores:
        text = f"{response.direct_answer} {response.main_observation}".strip()
        base = 95.0 if text else 0.0
        return EvalDimensionScores(
            relevance=base,
            specificity=base,
            completeness=base,
            clarity=base,
            usefulness=base,
            brevity=90.0 if len(text) < 600 else 75.0,
            tone=95.0,
            uncertainty_quality=95.0 if response.uncertainty_summary else 90.0,
            next_step_quality=95.0 if response.next_step else 90.0,
            language_quality=95.0,
        )

    def grade_real(self, *, prompt: str, response: VerifiedResponse, model: Optional[str] = None) -> tuple[EvalDimensionScores, Optional[str], dict]:
        result = openai_client.ask_gpt_structured_response(
            prompt=f"Question: {prompt}\nResponse: {response.dict()}",
            system_role="Score the response for relevance, specificity, completeness, clarity, usefulness, brevity, tone, uncertainty quality, next-step quality, and language quality on 0-100.",
            schema=self.SCHEMA,
            model_override=model,
            client_max_retries=0,
        )
        if result.get("error"):
            raise ValueError(str(result["error"]))
        parsed = result.get("parsed") or {}
        scores = EvalDimensionScores(**parsed)
        return scores, result.get("model"), result

