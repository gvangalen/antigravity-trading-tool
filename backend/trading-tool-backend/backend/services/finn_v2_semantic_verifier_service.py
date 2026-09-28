from __future__ import annotations

import asyncio
import logging
import re
from time import monotonic
from typing import Any, Dict, Optional

from backend.schemas.finn_v2_verifier_schema import SemanticVerificationResult
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds
from backend.utils import openai_client
from backend.utils.openai_client import StructuredOutputSpec


logger = logging.getLogger(__name__)


class FinnV2SemanticVerifierService:
    @staticmethod
    def _asserts_source_failure_cause(draft: Dict[str, Any]) -> bool:
        text = str(draft.get("direct_answer") or draft.get("content") or "")
        return bool(
            re.search(
                r"\b(?:provider|api|server|network|netwerk|bron|source|quelle)\b"
                r"[^.!?\n]{0,70}\b(?:down|failed|failing|broken|storing|uitval|"
                r"outage|ausfall|defekt|kapot|vertraagd|delayed)\b"
                r"|\b(?:missing|ontbrekende|fehlende|expired|verlopen)\s+"
                r"(?:api.key|credential|credentials|subscription|abonnement|zugangsdaten)\b"
                r"|\b(?:quota|rate.limit)\s+(?:exceeded|bereikt|überschritten)\b",
                text, re.IGNORECASE,
            )
            or re.search(
                r"\b(?:data|gegevens|bron|source|daten|quelle)\b[^.!?\n]{0,90}"
                r"\b(?:omdat|doordat|wegens|because|due to|weil|aufgrund)\b",
                text, re.IGNORECASE,
            )
        )

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
                "unsupported_unavailable_cause": {"type": "boolean"},
                "unverified_guardrail_override": {"type": "boolean"},
                "unverified_outcome_claim": {"type": "boolean"},
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
                "unsupported_unavailable_cause",
                "unverified_guardrail_override",
                "unverified_outcome_claim",
                "reason_codes",
            ],
    }
    COACH_SCHEMA = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "passes": {"type": "boolean"},
            "unsupported_unavailable_cause": {"type": "boolean"},
            "unverified_guardrail_override": {"type": "boolean"},
            "user_guardrail_quote": {"type": "string"},
            "draft_override_quote": {"type": "string"},
            "unverified_outcome_claim": {"type": "boolean"},
            "outcome_claim_quote": {"type": "string"},
            "reason_codes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "passes", "unsupported_unavailable_cause", "unverified_guardrail_override",
            "user_guardrail_quote", "draft_override_quote", "unverified_outcome_claim",
            "outcome_claim_quote", "reason_codes",
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
            "Set unsupported_unavailable_cause=true if the draft invents why an unavailable source is missing. "
            "Set unverified_guardrail_override=true if the draft encourages bypassing a precaution the user stated without verified current evidence. "
            "Set unverified_outcome_claim=true if it asserts that a trading rule increases success, improves entry, or reduces losses without evidence for that outcome. A conditional process rationale without an outcome promise is allowed. "
            "Either condition makes passes=false. "
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
        unsupported_cause = bool(parsed.get("unsupported_unavailable_cause"))
        guardrail_override = bool(parsed.get("unverified_guardrail_override"))
        outcome_claim = bool(parsed.get("unverified_outcome_claim"))
        return SemanticVerificationResult(
            available=True,
            passes=bool(parsed.get("passes")) and not (unsupported_cause or guardrail_override or outcome_claim),
            relevance_ok=bool(parsed.get("relevance_ok", True)),
            scope_ok=bool(parsed.get("scope_ok", True)),
            entailment_ok=bool(parsed.get("entailment_ok", True)),
            recommendation_ok=bool(parsed.get("recommendation_ok", True)),
            mode_purity_ok=bool(parsed.get("mode_purity_ok", True)),
            follow_up_ok=bool(parsed.get("follow_up_ok", True)),
            unsupported_unavailable_cause=unsupported_cause,
            unverified_guardrail_override=guardrail_override,
            unverified_outcome_claim=outcome_claim,
            reason_codes=[str(item) for item in parsed.get("reason_codes", []) if str(item)]
            + (["unsupported_cause"] if unsupported_cause else [])
            + (["unverified_guardrail_override"] if guardrail_override else [])
            + (["unverified_outcome_claim"] if outcome_claim else []),
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
        mandatory: bool = False,
        verification_guidance: str | None = None,
        coach_answer: bool = False,
    ) -> SemanticVerificationResult:
        """Verify through the cancellable provider transport."""
        if not mandatory and not self.flags.is_semantic_verifier_enabled():
            return SemanticVerificationResult(available=False, passes=True)

        verifier_model = (
            self.flags.coach_verifier_model() if coach_answer
            else self.flags.semantic_verifier_model()
        )
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
                model=verifier_model,
            )
        try:
            started = monotonic()
            response = await openai_client.ask_gpt_structured_response_async(
                prompt=str({
                    "user_message": user_message,
                    "draft": sanitized_draft,
                    "evidence": compact_evidence,
                    "deterministic_summary": deterministic_summary,
                }),
                system_role=(
                    "You are an independent verifier for FINN Core V2. "
                    "Only judge question relevance, scope completeness, entailment, recommendation consistency, "
                    "mode purity, and follow-up validity. Never reveal chain of thought. "
                    "Set unsupported_unavailable_cause=true if the draft invents why an unavailable source is missing. "
                    "Merely saying that a typed unavailable source has no data is supported; it does not explain why the source is unavailable. "
                    "Only flag an asserted cause (such as a provider outage, missing credential, or user action) when that cause is absent from the typed evidence. "
                    "Set unverified_guardrail_override=true if the draft encourages bypassing a precaution the user stated without verified current evidence. "
                    "For that flag, quote the exact user precaution in user_guardrail_quote and the exact draft advice to bypass it in draft_override_quote. Use empty strings otherwise. "
                    "Set unverified_outcome_claim=true if it asserts that a trading rule increases success, improves entry, or reduces losses without evidence for that outcome. A conditional process rationale without an outcome promise is allowed. "
                    "For that flag, quote the exact promised trading outcome in outcome_claim_quote; use an empty string otherwise. Describing a capability to calculate risk or review a plan is not an outcome promise. "
                    "Either condition makes passes=false. "
                    "Deterministic failures are final and cannot be overridden."
                    + (" " + verification_guidance if verification_guidance else "")
                ),
                output_spec=StructuredOutputSpec(
                    name="finn_v2_coach_verifier" if coach_answer else "finn_v2_semantic_verifier",
                    schema=self.COACH_SCHEMA if coach_answer else self.SCHEMA,
                ),
                model_override=verifier_model,
                timeout_seconds=effective_timeout,
                max_output_tokens=750 if coach_answer else 1000,
                client_max_retries=0,
            )
            logger.info(
                "FINN V2 semantic verifier async call finished",
                extra={
                    "stage": "semantic_verifier",
                    "mode": mode,
                    "model": response.get("model") or verifier_model,
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
                    model=verifier_model,
                )
            parsed = response.get("parsed") or {}
            reported_unavailable_cause = bool(parsed.get("unsupported_unavailable_cause"))
            unavailable_scopes = deterministic_summary.get("unavailable_scopes") or []
            unsupported_cause = reported_unavailable_cause and (
                not coach_answer or (
                    bool(unavailable_scopes)
                    and self._asserts_source_failure_cause(sanitized_draft)
                )
            )
            user_guardrail_quote = str(parsed.get("user_guardrail_quote") or "").strip()
            draft_override_quote = str(parsed.get("draft_override_quote") or "").strip()
            draft_text = str(sanitized_draft.get("direct_answer") or sanitized_draft.get("content") or "")
            guardrail_override = bool(parsed.get("unverified_guardrail_override")) and (
                len(user_guardrail_quote) >= 8
                and len(draft_override_quote) >= 8
                and user_guardrail_quote.casefold() in user_message.casefold()
                and draft_override_quote.casefold() in draft_text.casefold()
            ) if coach_answer else bool(parsed.get("unverified_guardrail_override"))
            outcome_quote = str(parsed.get("outcome_claim_quote") or "").strip()
            outcome_claim = bool(parsed.get("unverified_outcome_claim")) and (
                len(outcome_quote) >= 8
                and outcome_quote.casefold() in draft_text.casefold()
                and bool(re.search(
                    r"\b(?:guarantee|guarantees|guaranteed|garandeer\w*|garantier\w*|"
                    r"eliminat\w*\s+loss\w*|voorkom\w*\s+verlies|vermeid\w*\s+verlust\w*|"
                    r"increas\w*\s+(?:the\s+)?chance|verhoog\w*\s+(?:de\s+)?kans|"
                    r"improv\w*\s+(?:the\s+)?entry|betere\s+instap)\b",
                    outcome_quote, re.IGNORECASE,
                ))
            ) if coach_answer else bool(parsed.get("unverified_outcome_claim"))
            reason_codes = [str(item) for item in parsed.get("reason_codes", []) if str(item)]
            if coach_answer and not unsupported_cause:
                reason_codes = [
                    code for code in reason_codes
                    if code not in {"unsupported_unavailable_cause", "unsupported_cause"}
                ]
            if coach_answer and not guardrail_override:
                reason_codes = [
                    code for code in reason_codes
                    if code != "unverified_guardrail_override"
                ]
            if coach_answer and not outcome_claim:
                reason_codes = [
                    code for code in reason_codes
                    if code not in {"unverified_outcome_claim", "unsupported_outcome_claim"}
                ]
            unsupported_cause_only = (
                coach_answer and reported_unavailable_cause and not unsupported_cause
                and not reason_codes
            )
            unsupported_guardrail_only = (
                coach_answer and bool(parsed.get("unverified_guardrail_override"))
                and not guardrail_override and not reason_codes
            )
            unsupported_outcome_only = (
                coach_answer and bool(parsed.get("unverified_outcome_claim"))
                and not outcome_claim and not reason_codes
            )
            typed_ambiguity_question = (
                coach_answer
                and any(
                    str(item.get("reason") or "").endswith("_ambiguous")
                    for item in deterministic_summary.get("typed_unavailable_reasons") or []
                    if isinstance(item, dict)
                )
                and "?" in draft_text
                and bool(reason_codes)
                and set(reason_codes) <= {"setup_ambiguous", "scope_completeness"}
            )
            return SemanticVerificationResult(
                available=True,
                passes=(bool(parsed.get("passes")) or unsupported_cause_only
                or unsupported_guardrail_only or unsupported_outcome_only
                or typed_ambiguity_question)
                and not (unsupported_cause or guardrail_override or outcome_claim),
                relevance_ok=bool(parsed.get("relevance_ok", True)),
                scope_ok=bool(parsed.get("scope_ok", True)),
                entailment_ok=bool(parsed.get("entailment_ok", True)),
                recommendation_ok=bool(parsed.get("recommendation_ok", True)),
                mode_purity_ok=bool(parsed.get("mode_purity_ok", True)),
                follow_up_ok=bool(parsed.get("follow_up_ok", True)),
                unsupported_unavailable_cause=unsupported_cause,
                unverified_guardrail_override=guardrail_override,
                unverified_outcome_claim=outcome_claim,
                reason_codes=reason_codes
                + (["unsupported_cause"] if unsupported_cause else [])
                + (["unverified_guardrail_override"] if guardrail_override else [])
                + (["unverified_outcome_claim"] if outcome_claim else []),
                model=response.get("model") or verifier_model,
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
                model=verifier_model,
            )
