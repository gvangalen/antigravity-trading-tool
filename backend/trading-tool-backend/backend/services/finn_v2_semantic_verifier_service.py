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
    def _negates_guardrail_override(draft_text: str, quote: str) -> bool:
        start = draft_text.casefold().find(quote.casefold())
        if start < 0:
            return False
        clause = draft_text[max(0, start - 35):start + len(quote) + 25]
        negation_before = re.search(
            r"\b(?:don['’]t|do not|shouldn['’]t|wouldn['’]t|never|"
            r"niet|nooit|nicht|niemals)\b[^.!?\n]{0,35}"
            r"\b(?:ignore|bypass|skip|negeer\w*|omzeil\w*|oversla\w*|"
            r"ignorier\w*|umgeh\w*)\b",
            clause, re.IGNORECASE,
        )
        negation_after = re.search(
            r"\b(?:negeer\w*|omzeil\w*|ignorier\w*|umgeh\w*)\b"
            r"[^.!?\n]{0,45}\b(?:niet|nooit|nicht|niemals)\b",
            clause, re.IGNORECASE,
        )
        return bool(negation_before or negation_after)

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
            "unsupported_personal_claim_quote": {"type": "string"},
            "reason_codes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "passes", "unsupported_unavailable_cause", "unverified_guardrail_override",
            "user_guardrail_quote", "draft_override_quote", "unverified_outcome_claim",
            "outcome_claim_quote", "reason_codes",
            "unsupported_personal_claim_quote",
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
                    (
                        "You verify hard safety and evidence boundaries, not coaching style. "
                        "The current user statement and previous_user_message are user statements, "
                        "not proof of a saved FINN fact. Evidence is authoritative only for the "
                        "owner-scoped facts it actually contains. Reject invented saved object "
                        "names, fields, current market data, or promised trading outcomes; quote "
                        "the exact unsupported answer span. "
                        "A typed evaluation_incomplete result cannot support a positive fit or "
                        "suitability conclusion, even if the answer hedges that conclusion. "
                        "Acknowledge verified settings separately from suitability. "
                        "If the user says they must wait for a condition before entering a trade, "
                        "reject ANY advice "
                        "to enter before it, including conditional alternatives, smaller positions, "
                        "or an exit plan. Quote the exact user condition and the exact advice span. "
                        "Do not reject an answer that only explains the user's condition, suggests "
                        "waiting, or offers a non-trading coping step. Return empty quote strings "
                        "when no corresponding violation exists. Do not infer a violation from a "
                        "reason label alone. Never reveal chain of thought. "
                        + (verification_guidance or "")
                    ) if coach_answer else (
                    "You are an independent verifier for FINN Core V2. "
                    "Only judge question relevance, scope completeness, entailment, recommendation consistency, "
                    "mode purity, and follow-up validity. Never reveal chain of thought. "
                    "The user_message field is the current user turn. A previous_verified_answer "
                    "in deterministic_summary is prior assistant text: it can explain a follow-up "
                    "or preserve a precaution, but it is not by itself proof of a saved FINN fact. "
                    "A previous_user_message is a prior user statement, not a persisted account fact. "
                    "Set unsupported_unavailable_cause=true if the draft invents why an unavailable source is missing. "
                    "Merely saying that a typed unavailable source has no data is supported; it does not explain why the source is unavailable. "
                    "Only flag an asserted cause (such as a provider outage, missing credential, or user action) when that cause is absent from the typed evidence. "
                    "Set unverified_guardrail_override=true if the draft encourages bypassing a precaution the user stated without verified current evidence. A suggested smaller or partial position before the stated entry trigger, even with an exit plan or risk controls, is a bypass rather than a safe compromise. "
                    "Do not flag advice to keep that precaution, to wait for its condition, or to reconsider it later outside the pressured decision. Judge the advice's polarity, not the mere mention of bypassing. "
                    "For that flag, quote the exact user precaution in user_guardrail_quote and the exact draft advice to bypass it in draft_override_quote. Use empty strings otherwise. "
                    "Set unverified_outcome_claim=true if it asserts that a trading rule increases success, improves entry, or reduces losses without evidence for that outcome. A conditional process rationale without an outcome promise is allowed. "
                    "For that flag, quote the exact promised trading outcome in outcome_claim_quote; use an empty string otherwise. Describing a capability to calculate risk or review a plan is not an outcome promise. "
                    "When an evaluation lacks required evidence, even a hedged assertion that a saved plan suits the user's goals or risk style is an unverified personal claim. A rule described by the user is not a verified saved rule: without a completed read proving it, attributing that rule to a saved plan or setup is also an unverified personal claim. Put unverified_personal_claim in reason_codes and set passes=false; reporting known saved settings, attributing a rule to the trader, and explaining the evaluation limit are allowed. "
                    "For an unverified personal claim, quote the exact unsupported words from the draft in unsupported_personal_claim_quote; otherwise use an empty string. "
                    "Either condition makes passes=false. "
                    "Deterministic failures are final and cannot be overridden."
                    + (" " + verification_guidance if verification_guidance else "")
                    )
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
            prior_verified_answer = str(deterministic_summary.get("previous_verified_answer") or "")
            prior_user_message = str(deterministic_summary.get("previous_user_message") or "")
            guardrail_override = bool(parsed.get("unverified_guardrail_override")) and (
                len(user_guardrail_quote) >= 8
                and len(draft_override_quote) >= 8
                and (user_guardrail_quote.casefold() in user_message.casefold()
                     or user_guardrail_quote.casefold() in prior_user_message.casefold()
                     or user_guardrail_quote.casefold() in prior_verified_answer.casefold())
                and draft_override_quote.casefold() in draft_text.casefold()
                and not self._negates_guardrail_override(draft_text, draft_override_quote)
            ) if coach_answer else bool(parsed.get("unverified_guardrail_override"))
            outcome_quote = str(parsed.get("outcome_claim_quote") or "").strip()
            personal_claim_quote = str(parsed.get("unsupported_personal_claim_quote") or "").strip()
            personal_claim_supported = (
                len(personal_claim_quote) >= 8
                and personal_claim_quote.casefold() in draft_text.casefold()
            )
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
            coach_scope_only = coach_answer and bool(reason_codes) and set(reason_codes) <= {"scope_incomplete"}
            if coach_scope_only:
                reason_codes = []
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
            if coach_answer and not personal_claim_supported:
                reason_codes = [
                    code for code in reason_codes
                    if code != "unverified_personal_claim"
                ]
            if coach_answer:
                # Advisory judgments are not a second coach policy. Hard evidence and
                # safety checks remain in this verifier and the deterministic audit.
                hard_reasons = {
                    "setup_ambiguous", "scope_completeness", "unverified_personal_claim",
                    "unsupported_unavailable_cause", "unsupported_cause",
                    "unverified_guardrail_override", "unverified_outcome_claim",
                    "unsupported_outcome_claim",
                }
                reason_codes = [code for code in reason_codes if code in hard_reasons]
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
            coach_advisory_only = (
                coach_answer and not reason_codes
                and not (unsupported_cause or guardrail_override or outcome_claim)
            )
            return SemanticVerificationResult(
                available=True,
                passes=(bool(parsed.get("passes")) or unsupported_cause_only
                or unsupported_guardrail_only or unsupported_outcome_only
                or typed_ambiguity_question or coach_scope_only or coach_advisory_only)
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
                rejected_claim_quotes=[quote for quote in (
                    draft_override_quote if guardrail_override else "",
                    outcome_quote if outcome_claim else "",
                    personal_claim_quote if "unverified_personal_claim" in reason_codes else "",
                ) if len(quote) >= 8 and quote.casefold() in draft_text.casefold()],
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
