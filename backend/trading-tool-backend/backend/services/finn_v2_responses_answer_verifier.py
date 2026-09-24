"""Verify a model-composed read answer against owner-scoped tool evidence."""

from __future__ import annotations

from dataclasses import dataclass
import asyncio
import json
from typing import Any
from langdetect import DetectorFactory, LangDetectException, detect

from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds


@dataclass(frozen=True)
class FinnResponsesVerifiedAnswer:
    status: str
    text: str
    reason: str | None
    evidence: tuple[dict[str, Any], ...]
    used_previous_response: bool = False


class FinnResponsesAnswerVerifier:
    def __init__(self, semantic: FinnV2SemanticVerifierService | None = None, client: Any = None) -> None:
        self.semantic = semantic or FinnV2SemanticVerifierService()
        self.client = client

    @staticmethod
    def _fallback_language(message: str, previous_answer: str = "") -> str:
        DetectorFactory.seed = 0
        brief = message.strip().casefold().rstrip("?!. ")
        if brief in {"why", "how"}:
            return "en"
        if brief in {"warum", "wieso", "weshalb"}:
            return "de"
        if brief in {"waarom", "hoe"}:
            return "nl"
        for sample in (message, previous_answer):
            if not sample.strip():
                continue
            try:
                language = detect(sample)
            except LangDetectException:
                continue
            if language in {"nl", "en", "de"}:
                return language
        return "nl"

    @classmethod
    def _fallback_copy(cls, reason: str, *, message: str, previous_answer: str = "") -> str:
        language = cls._fallback_language(message, previous_answer)
        copies = {
            "setup_ambiguous": {
                "nl": "Ik zie meerdere setups. Welke wil je als uitgangspunt voor je plan gebruiken?",
                "en": "I found several setups. Which one should I use as the basis for your plan?",
                "de": "Ich sehe mehrere Setups. Welches soll ich als Grundlage für deinen Plan verwenden?",
            },
            "source_unavailable": {
                "nl": "Ik heb hiervoor geen betrouwbare actuele gegevens. Zonder die bron kan ik dit nog niet beoordelen.",
                "en": "I don't have reliable current data for this. Without that source, I can't assess it yet.",
                "de": "Mir fehlen dafür verlässliche aktuelle Daten. Ohne diese Quelle kann ich es noch nicht beurteilen.",
            },
            "previous_source_unavailable": {
                "nl": "Ik kan de oorzaak van de ontbrekende gegevens niet vaststellen. Daarom kan ik het effect op je plan nog niet betrouwbaar beoordelen.",
                "en": "I can't establish why the data is missing, so I can't reliably assess its effect on your plan yet.",
                "de": "Ich kann die Ursache der fehlenden Daten nicht feststellen und ihre Auswirkung auf deinen Plan daher noch nicht zuverlässig beurteilen.",
            },
        }
        return copies.get(reason, {}).get(language) or {
            "nl": "Ik kan dit nog niet onderbouwen met betrouwbare gegevens.",
            "en": "I can't support this with reliable evidence yet.",
            "de": "Ich kann das noch nicht mit verlässlichen Daten belegen.",
        }[language]

    @staticmethod
    def _typed_failure_reason(evidence: tuple[dict[str, Any], ...]) -> str:
        reasons = {
            str(item.get("reason") or "")
            for item in evidence if item.get("status") != "completed"
        }
        if "setup_ambiguous" in reasons:
            return "setup_ambiguous"
        unavailable_scopes = {
            str(item.get("scope")) for item in evidence
            if item.get("status") != "completed" and item.get("reason") == "source_unavailable"
        }
        if unavailable_scopes and not any(
            item.get("status") == "completed" and str(item.get("scope")) in unavailable_scopes
            for item in evidence
        ):
            return "source_unavailable"
        if evidence and all(item.get("status") != "completed" for item in evidence):
            return "source_unavailable"
        if not evidence:
            return "no_evidence_available"
        return "responses_evidence_not_verified"

    async def _cause_claim_is_grounded(self, *, answer: str, remaining: float | None) -> bool:
        if self.client is None or (remaining is not None and remaining <= 4):
            return False
        timeout = min(3.0, remaining - 3 if remaining is not None else 3.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o-mini", store=False, tool_choice="none",
                    instructions=(
                        "Independently audit this FINN answer. The only verified fact is that current "
                        "source data is unavailable; the reason is NOT known. Does the answer assert or "
                        "suggest any cause, including a technical problem, delay, provider issue, or "
                        "temporary outage? Return unsupported_cause=true if it does. Do not treat "
                        "'source_unavailable' as evidence for a cause."
                    ),
                    input=answer,
                    text={"format": {
                        "type": "json_schema", "name": "finn_unavailable_cause_check", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"unsupported_cause": {"type": "boolean"}},
                            "required": ["unsupported_cause"],
                        },
                    }},
                    max_output_tokens=60,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            return parsed.get("unsupported_cause") is False
        except Exception:
            return False

    async def verify(
        self, *, message: str, result: FinnResponsesResult,
        previous_response: dict[str, Any] | None = None,
        recent_action_result: dict[str, Any] | None = None,
    ) -> FinnResponsesVerifiedAnswer:
        evidence = tuple(
            item
            for call in result.tool_trace
            for item in (call.get("result", {}).get("results") or [])
            if isinstance(item, dict)
        )
        if any(call.get("status") == "error" for call in result.tool_trace):
            return FinnResponsesVerifiedAnswer(
                "unavailable", "Ik kan dit nu niet betrouwbaar beoordelen.",
                "responses_tool_execution_failed", evidence,
            )
        compact = [
            {
                "scope": item.get("scope"), "status": item.get("status"),
                "source": item.get("source"),
                "as_of": item.get("as_of"), "asset": item.get("asset"),
                "freshness": item.get("freshness"), "availability": item.get("availability"),
                "data": item.get("data"), "reason": item.get("reason"),
            }
            for item in evidence
        ]
        previous_answer = str((previous_response or {}).get("answer") or "").strip()
        confirmed_action = {
            key: recent_action_result.get(key)
            for key in ("operation_id", "entity_type", "canonical_name", "result_status")
            if recent_action_result and recent_action_result.get(key) is not None
        }
        general_education = bool(result.tool_trace) and all(
            call.get("name") == "answer_directly" for call in result.tool_trace
        )
        previous_source_evidence = [
            item for call in (previous_response or {}).get("tool_trace", [])
            for item in (call.get("result", {}).get("results") or [])
            if isinstance(item, dict)
        ]
        current_scopes = {item.get("scope") for item in evidence}
        relevant_previous_source_evidence = [
            item for item in previous_source_evidence
            if not current_scopes or item.get("scope") in current_scopes
        ]
        unavailable_without_cause = any(
            item.get("reason") == "source_unavailable"
            for item in (*evidence, *relevant_previous_source_evidence)
        )
        limitation_only = bool(evidence) and all(item.get("status") != "completed" for item in evidence)
        if previous_answer:
            compact.append({
                "scope": "previous_response",
                "source": "owner_scoped_runtime_contract",
                "availability": "available",
                "data": {
                    "answer": previous_answer,
                    "source_evidence": previous_source_evidence,
                },
            })
        if confirmed_action.get("result_status") == "succeeded":
            compact.append({
                "scope": "confirmed_action_result",
                "source": "owner_scoped_runtime_contract",
                "availability": "available",
                "data": confirmed_action,
            })
        guidance = (
                "This is a Responses-tool-loop answer, not a selector-first contract response. "
                "Check every concrete personal or market fact against the supplied typed tool evidence, "
                "including asset, timeframe, freshness and unavailable states. General educational "
                "explanations and an honest statement that personal data is unavailable do not require "
                "unrelated extra tools or a fully populated profile. Do not demand every possible "
                "scope when the answer explicitly limits itself to available evidence. If a previous "
                "verified response appears in evidence, interpret short follow-up questions relative "
                "to that response, but reject invented causes, technical failures or unsupported advice."
                " Judge source availability per claim and question, not per bundled tool. A completed "
                "owner-scoped indicator_configuration with an empty category list proves that the "
                "user has no saved indicators in that category. An unavailable technical or market "
                "snapshot does not invalidate that configuration fact or ordinary educational reasons "
                "for considering a category; it only prevents claims about current indicator values "
                "or market effects. Conversely, never infer a current value from saved configuration."
                " Active indicator options supplied by the canonical indicator catalog can ground "
                "a recommendation of what to configure next, but not a claim about its current reading. "
                "The available_macro_indicator_catalog scope lists supported options that are "
                "deliberately NOT in the user's saved configuration; recommending one of them "
                "does not claim it is already saved."
                " A confirmed_action_result is verified persisted evidence of the object just saved. "
                "For a claim about which object was saved, its exact canonical_name must match this "
                "result; a short guided slot answer is not an object's name unless this result says so. "
                "Do not invent saved object names from conversation text. This action result proves "
                "only object identity and successful persistence, not its current asset, timeframe, "
                "frequency, amount, currency or other fields. Previous chat text and a draft are "
                "not a saved-object read. If an answer describes any such object fields, require a "
                "completed owner-scoped read of that object type in the current tool trace; "
                "read_review_history and read_latest_report do not satisfy setup/strategy/bot "
                "field claims. Reject unsupported extra details even when the saved name is correct."
                " Also verify that the answer addresses the user's actual request. If the user explicitly "
                "asked to create, update or delete a saved object, a read-only explanation or request "
                "for profile details does not fulfill that action request. Reject it so FINN can retry "
                "with the registry-backed proposal tool; missing action inputs are collected by that tool."
                " When typed tools report unavailable or stale, an answer that accurately states "
                "the limitation and does not invent prices, dates or conclusions is supported by "
                "that unavailable evidence; source_unavailable alone is not a reason to reject it."
                + (
                    " All requested tool sources are unavailable here. Verify whether the answer "
                    "only acknowledges that limitation for the requested assets and refrains from "
                    "invented prices, dates, causes, financial conclusions or advice. Such a limited "
                    "answer is fully supported by these typed unavailable results and should pass."
                    if limitation_only else ""
                )
                + (
                    " The typed source_unavailable reason establishes only that current data cannot "
                    "be read. It does NOT establish a technical outage, provider failure, temporary "
                    "disruption, or any other cause. Reject any asserted cause unless it is separately "
                    "and explicitly evidenced by a tool result."
                    if unavailable_without_cause else ""
                )
                + (
                    " This is a general educational explanation selected through answer_directly. "
                    "Check ordinary conceptual accuracy and absence of personal or current-market claims. "
                    "Do not require any profile, plan, market or owner-scoped evidence for a general definition."
                    if general_education else ""
                )
        )
        mode = "EXPLAIN" if previous_answer or general_education else "UNAVAILABLE" if limitation_only else "READ"
        user_message = (
            f"Previous verified response: {previous_answer}\nCurrent user follow-up: {message}"
            if previous_answer else message
        )
        summary = {
            "available_scopes": [item.get("scope") for item in evidence if item.get("status") == "completed"]
            + (["previous_response"] if previous_answer else [])
            + (["confirmed_action_result"] if confirmed_action.get("result_status") == "succeeded" else []),
            "unavailable_scopes": [item.get("scope") for item in evidence if item.get("status") != "completed"],
            "unavailable_cause_established": False if unavailable_without_cause else None,
            "general_education_no_personal_claims": general_education,
        }

        async def verify_text(text: str):
            return await self.semantic.verify_async(
                mode=mode, user_message=user_message, mandatory=True,
                verification_guidance=guidance,
                sanitized_draft={"mode": mode, "direct_answer": text},
                compact_evidence=compact, deterministic_summary=summary,
            )

        verdict = await verify_text(result.text)
        if verdict.available and verdict.passes and previous_answer and unavailable_without_cause:
            if not await self._cause_claim_is_grounded(
                answer=result.text, remaining=remaining_lifecycle_seconds(),
            ):
                return FinnResponsesVerifiedAnswer(
                    "unavailable",
                    self._fallback_copy("previous_source_unavailable", message=message, previous_answer=previous_answer),
                    "source_unavailable", evidence, True,
                )
        if verdict.available and not verdict.passes and self.client is not None:
            remaining = remaining_lifecycle_seconds()
            if remaining is None or remaining > 8:
                try:
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model="gpt-4o-mini", store=False,
                            instructions=(
                                "You are FINN. Rewrite the answer in the user's language using ONLY the "
                                "typed evidence and previous verified answer provided. The prior draft was "
                                "rejected as unsupported. State unavailable data and unknown causes plainly; "
                                "do not invent prices, user facts, recommendations or provider failures. "
                                "Do not replace an explicit action request with a read-only answer; "
                                "without a proposal tool result, do not claim the action was prepared. "
                                "Keep it brief and natural. Never expose internal IDs or reason codes."
                            ),
                            input=json.dumps({
                                "question": user_message, "evidence": compact,
                                "rejected_draft": result.text,
                                "rejection_reasons": verdict.reason_codes,
                            }, ensure_ascii=False, default=str),
                            tool_choice="none",
                        ),
                        timeout=min(8.0, remaining - 3 if remaining is not None else 8.0),
                    )
                    revised = str(getattr(response, "output_text", "") or "").strip()
                    if not revised:
                        revised = "\n".join(
                            str(getattr(part, "text", "") or "")
                            for item in (getattr(response, "output", None) or [])
                            if getattr(item, "type", None) == "message"
                            for part in (getattr(item, "content", None) or [])
                            if getattr(part, "type", None) == "output_text"
                        ).strip()
                    if revised:
                        revised_verdict = await verify_text(revised)
                        if revised_verdict.available and revised_verdict.passes:
                            if previous_answer and unavailable_without_cause and not await self._cause_claim_is_grounded(
                                answer=revised, remaining=remaining_lifecycle_seconds(),
                            ):
                                return FinnResponsesVerifiedAnswer(
                                    "unavailable",
                                    self._fallback_copy("previous_source_unavailable", message=message, previous_answer=previous_answer),
                                    "source_unavailable", evidence, True,
                                )
                            return FinnResponsesVerifiedAnswer(
                                "completed", revised, None, evidence, bool(previous_answer),
                            )
                except Exception:
                    pass
        if not verdict.available or not verdict.passes:
            reason = self._typed_failure_reason((*evidence, *relevant_previous_source_evidence))
            answer = self._fallback_copy(
                "previous_source_unavailable" if previous_answer and unavailable_without_cause else reason,
                message=message, previous_answer=previous_answer,
            )
            return FinnResponsesVerifiedAnswer(
                "unavailable", answer, reason, evidence, bool(previous_answer),
            )
        return FinnResponsesVerifiedAnswer("completed", result.text, None, evidence, bool(previous_answer))
