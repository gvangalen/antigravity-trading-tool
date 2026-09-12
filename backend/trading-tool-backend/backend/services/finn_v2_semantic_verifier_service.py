from __future__ import annotations

import asyncio
import logging
from time import monotonic
from typing import Any, Dict, Optional

from backend.schemas.finn_v2_verifier_schema import SemanticVerificationResult
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds
from backend.utils import openai_client
from backend.utils.openai_client import StructuredOutputSpec


logger = logging.getLogger(__name__)


class FinnV2SemanticVerifierService:
    SCHEMA = {
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
        provider_timeout_seconds: float | None = None,
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
            output_spec=StructuredOutputSpec(name="finn_v2_semantic_verifier", schema=self.SCHEMA),
            model_override=self.flags.semantic_verifier_model(),
            timeout_seconds=provider_timeout_seconds or self.flags.semantic_verifier_timeout_seconds(),
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

    async def verify_async(
        self,
        *,
        mode: str,
        user_message: str,
        sanitized_draft: Dict[str, Any],
        compact_evidence: list[dict],
        deterministic_summary: Dict[str, Any],
        timeout_seconds: float | None = None,
    ) -> SemanticVerificationResult:
        """Run the synchronous provider client without blocking the worker loop.

        The lifecycle deadline runs on that loop. Calling the legacy sync client
        directly made a slow verifier invisible to cancellation and starved later
        interactive runs. The sync request has its own bounded provider timeout;
        this outer bound keeps lifecycle terminalisation responsive as well.
        """
        if not self.flags.is_semantic_verifier_enabled():
            return SemanticVerificationResult(available=False, passes=True)

        configured_timeout = float(self.flags.semantic_verifier_timeout_seconds())
        remaining = remaining_lifecycle_seconds()
        if remaining is not None:
            remaining = max(0.0, remaining)
        effective_timeout = max(
            0.1,
            min(configured_timeout, timeout_seconds or configured_timeout, remaining if remaining is not None else configured_timeout),
        )
        if remaining is not None and remaining < 0.25:
            return SemanticVerificationResult(
                available=False,
                passes=False,
                reason_codes=["semantic_verifier_budget_exhausted"],
                model=self.flags.semantic_verifier_model(),
            )
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(
                    self.verify,
                    mode=mode,
                    user_message=user_message,
                    sanitized_draft=sanitized_draft,
                    compact_evidence=compact_evidence,
                    deterministic_summary=deterministic_summary,
                    provider_timeout_seconds=effective_timeout,
                ),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning(
                "FINN V2 semantic verifier timed out",
                extra={"stage": "semantic_verifier", "mode": mode, "timeout_seconds": effective_timeout},
            )
            return SemanticVerificationResult(
                available=False,
                passes=False,
                reason_codes=["semantic_verifier_timeout"],
                model=self.flags.semantic_verifier_model(),
            )
