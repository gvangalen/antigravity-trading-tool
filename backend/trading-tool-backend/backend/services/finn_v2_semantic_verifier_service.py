from __future__ import annotations

import logging
from time import monotonic
from typing import Any, Dict, Optional

from backend.schemas.finn_v2_verifier_schema import SemanticVerificationResult
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.utils import openai_client


logger = logging.getLogger(__name__)


class FinnV2SemanticVerifierService:
    SCHEMA = {
        "name": "finn_v2_semantic_verifier",
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "passes": {"type": "boolean"},
                "relevance_ok": {"type": "boolean"},
                "scope_ok": {"type": "boolean"},
                "entailment_ok": {"type": "boolean"},
                "recommendation_ok": {"type": "boolean"},
                "mode_purity_ok": {"type": "boolean"},
                "follow_up_ok": {"type": "boolean"},
                "reason_codes": {"type": "array", "items": {"type": "string"}},
            },
            "required": [
                "passes",
                "relevance_ok",
                "scope_ok",
                "entailment_ok",
                "recommendation_ok",
                "mode_purity_ok",
                "follow_up_ok",
                "reason_codes",
            ],
        },
        "strict": True,
    }

    def __init__(self, flag_service: Optional[FinnV2FlagService] = None):
        self.flags = flag_service or FinnV2FlagService()

    def verify(
        self,
        *,
        mode: str,
        user_message: str,
        sanitized_draft: Dict[str, Any],
        compact_evidence: list[dict],
        deterministic_summary: Dict[str, Any],
    ) -> SemanticVerificationResult:
        if not self.flags.is_semantic_verifier_enabled():
            return SemanticVerificationResult(available=False, passes=True)

        system_prompt = (
            "You are an independent verifier for FINN Core V2. "
            "Only judge question relevance, scope completeness, entailment, recommendation consistency, mode purity, and follow-up validity. "
            "Never reveal chain of thought. Deterministic failures are final and cannot be overridden."
        )
        user_prompt = {
            "user_message": user_message,
            "draft": sanitized_draft,
            "evidence": compact_evidence,
            "deterministic_summary": deterministic_summary,
        }
        started = monotonic()
        response = openai_client.ask_gpt_structured_response(
            prompt=str(user_prompt),
            system_role=system_prompt,
            schema=self.SCHEMA,
            model_override=self.flags.semantic_verifier_model(),
            timeout_seconds=self.flags.semantic_verifier_timeout_seconds(),
            client_max_retries=0,
        )
        logger.info(
            "FINN V2 semantic verifier call finished",
            extra={
                "stage": "semantic_verifier",
                "mode": mode,
                "model": response.get("model") or self.flags.semantic_verifier_model(),
                "latency_ms": int((monotonic() - started) * 1000),
                "output_status": "error" if response.get("error") else "ok",
                "error_code": response.get("error"),
            },
        )
        if response.get("error"):
            return SemanticVerificationResult(
                available=False,
                passes=False,
                reason_codes=[str(response["error"])],
                model=self.flags.semantic_verifier_model(),
            )
        parsed = response.get("parsed") or {}
        return SemanticVerificationResult(
            available=True,
            passes=bool(parsed.get("passes")),
            relevance_ok=bool(parsed.get("relevance_ok", True)),
            scope_ok=bool(parsed.get("scope_ok", True)),
            entailment_ok=bool(parsed.get("entailment_ok", True)),
            recommendation_ok=bool(parsed.get("recommendation_ok", True)),
            mode_purity_ok=bool(parsed.get("mode_purity_ok", True)),
            follow_up_ok=bool(parsed.get("follow_up_ok", True)),
            reason_codes=[str(item) for item in parsed.get("reason_codes", []) if str(item)],
            model=response.get("model"),
        )
