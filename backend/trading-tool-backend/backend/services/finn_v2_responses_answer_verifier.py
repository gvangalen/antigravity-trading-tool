"""Verify a model-composed read answer against owner-scoped tool evidence."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import asyncio
import json
import logging
import re
from typing import Any
from langdetect import DetectorFactory, LangDetectException, detect

from backend.services.finn_v2_responses_loop import FinnResponsesResult
from backend.services.finn_v2_semantic_verifier_service import FinnV2SemanticVerifierService
from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinnResponsesVerifiedAnswer:
    status: str
    text: str
    reason: str | None
    evidence: tuple[dict[str, Any], ...]
    used_previous_response: bool = False
    clarification: dict[str, str] | None = None


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

    @staticmethod
    def _contains_internal_identifier(text: str) -> bool:
        return bool(re.search(
            r"\bfinn-v2-(?:run|conv|proposal|execution|contract)-[\w-]+\b"
            r"|\b(?:setup|strategy|bot|proposal|execution|run)[\s_-]*id\s*[:#=]",
            text, re.IGNORECASE,
        ))

    @staticmethod
    def _currency_amounts(text: str) -> set[str]:
        amounts = set()
        for match in re.finditer(
            r"(?:[€$]\s*([\d][\d.,]*)|([\d][\d.,]*)\s*(?:[€$]|\beuro\b|\beur\b|\busd\b|\bdollar\b))",
            text.casefold(),
        ):
            value = (match.group(1) or match.group(2)).rstrip(".,")
            if "," in value and "." in value:
                decimal_separator = "," if value.rfind(",") > value.rfind(".") else "."
            elif "," in value or "." in value:
                separator = "," if "," in value else "."
                decimal_separator = separator if len(value.rsplit(separator, 1)[-1]) <= 2 else ""
            else:
                decimal_separator = ""
            normalized = "".join(
                "." if character == decimal_separator else character
                for character in value if character.isdigit() or character == decimal_separator
            )
            try:
                amounts.add(str(Decimal(normalized).normalize()))
            except InvalidOperation:
                pass
        return amounts

    @classmethod
    def _amounts_supported(
        cls, *, answer: str, message: str, previous_answer: str,
        evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        claims = cls._currency_amounts(answer)
        if not claims:
            return True
        grounded = cls._currency_amounts(message) | cls._currency_amounts(previous_answer)

        def monetary_fields(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if any(token in str(key).casefold() for token in ("amount", "budget", "investment")):
                        grounded.update(cls._currency_amounts(f"€{item}"))
                    else:
                        monetary_fields(item)
            elif isinstance(value, list):
                for item in value:
                    monetary_fields(item)

        for item in evidence:
            if item.get("status") == "completed":
                monetary_fields(item.get("data"))
        return claims <= grounded

    @staticmethod
    def _asset_quantities_supported(
        *, answer: str, message: str, evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        assets = {
            str(item.get("asset") or "").upper()
            for item in evidence if item.get("status") == "completed"
        }
        for asset in assets:
            if not re.fullmatch(r"[A-Z]{2,8}", asset):
                continue
            quantity = re.compile(rf"\b\d+(?:[.,]\d+)?\s+{re.escape(asset)}\b", re.IGNORECASE)
            claims = {match.group().casefold() for match in quantity.finditer(answer)}
            if claims and not claims <= {match.group().casefold() for match in quantity.finditer(message)}:
                return False
        return True

    @staticmethod
    def _currency_units_supported(
        *, answer: str, message: str, evidence: tuple[dict[str, Any], ...],
    ) -> bool:
        def units(text: str) -> set[str]:
            normalized = text.casefold()
            found = set()
            if re.search(r"(?:€\s*\d|\d\s*€|\d\s*(?:eur|euro)\b)", normalized):
                found.add("EUR")
            if re.search(r"(?:\$\s*\d|\d\s*\$|\d\s*(?:usd|dollar)\b)", normalized):
                found.add("USD")
            return found

        claimed = units(answer)
        allowed = units(message)

        def collect_currency(value: Any) -> None:
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {"currency", "base_currency", "quote_currency"}:
                        if str(item).upper() in {"EUR", "USD"}:
                            allowed.add(str(item).upper())
                    else:
                        collect_currency(item)
            elif isinstance(value, list):
                for item in value:
                    collect_currency(item)

        for item in evidence:
            if item.get("status") == "completed":
                collect_currency(item.get("data"))
        return claimed <= allowed

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

    async def _personal_advice_is_grounded(
        self, *, answer: str, evidence: list[dict[str, Any]], remaining: float | None,
        question: str | None = None,
    ) -> bool:
        if self.client is None:
            return False
        if remaining is not None and remaining <= 5:
            logger.info("FINN personal advice audit skipped: lifecycle budget", extra={
                "stage": "responses_personal_advice_audit", "reason": "insufficient_lifecycle_budget",
                "remaining_seconds": round(remaining, 2),
            })
            return False
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    instructions=(
                        "Audit a trading-coach answer against ONLY the typed evidence. Distinguish "
                        "stored user choices from evaluated market/risk evidence. A saved profile, "
                        "setup, strategy, entry, stop-loss or target proves its stored value, NOT "
                        "personal suitability, profitability, historical market conditions, a "
                        "need to change levels, or that changes will achieve investment goals. "
                        "General education, cautious questions, truthful descriptions of saved "
                        "settings, and invitations to CHECK suitability by obtaining current "
                        "market or owner-scoped risk evidence are allowed. 'Check whether these "
                        "saved levels suit your risk profile' does NOT claim they suit it. "
                        "Mark unsupported_personal_advice true if "
                        "the answer implies any unevidenced personal recommendation, causal "
                        "market history, or suitability claim. In particular, if a saved entry "
                        "is 100, a stop is 90 and a target is 120, 'the saved settings are 100, "
                        "90 and 120' is factual. 'Begin investing at 100', 'set your stop at "
                        "90', 'take profit at 120', or 'this structure offers strategic "
                        "advantage' are recommendations, NOT established facts. Mark those "
                        "unsupported unless an explicit current owner-scoped evaluation supports "
                        "them. Do not assume missing evidence. If a question is supplied, also "
                        "judge whether the answer directly addresses it using verified saved "
                        "settings, or honestly says that suitability is not yet established and "
                        "offers the missing evaluation. Such a limited answer IS complete for a "
                        "request for a logical personal plan when no current evaluation exists. "
                        "A generic refusal or a repeated setup-choice question is not complete. "
                        "When no question is supplied, set addresses_request=true."
                    ),
                    input=json.dumps(
                        {"answer": answer, "evidence": evidence, "question": question},
                        ensure_ascii=False, default=str,
                    ),
                    text={"format": {
                        "type": "json_schema", "name": "finn_personal_advice_check", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "unsupported_personal_advice": {"type": "boolean"},
                                "addresses_request": {"type": "boolean"},
                            },
                            "required": ["unsupported_personal_advice", "addresses_request"],
                        },
                    }},
                    max_output_tokens=60,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            if parsed.get("unsupported_personal_advice") is not False:
                logger.info("FINN personal advice audit rejected answer", extra={
                    "stage": "responses_personal_advice_audit", "reason": "unsupported_personal_advice",
                })
            return parsed.get("unsupported_personal_advice") is False and (
                question is None or parsed.get("addresses_request") is True
            )
        except Exception as exc:
            logger.info("FINN personal advice audit unavailable: %s", type(exc).__name__, extra={
                "stage": "responses_personal_advice_audit", "reason": "audit_unavailable",
            })
            return False

    async def _technical_limitation_is_grounded(
        self, *, answer: str, remaining: float | None,
    ) -> bool:
        if self.client is None or (remaining is not None and remaining <= 5):
            return False
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    instructions=(
                        "Audit this answer to a question about current technical indicators. "
                        "The current technical snapshot is unavailable. Do not infer a temporary "
                        "outage, provider failure, delay or other cause. Do not claim a current RSI, "
                        "moving-average reading, or combined market signal. General educational "
                        "statements must also be materially correct: RSI above 70 is commonly "
                        "called overbought and below 30 oversold, not the reverse. Flag any "
                        "unsupported cause, invented reading, or material technical error."
                    ),
                    input=answer,
                    text={"format": {
                        "type": "json_schema", "name": "finn_technical_limitation_check", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"grounded": {"type": "boolean"}},
                            "required": ["grounded"],
                        },
                    }},
                    max_output_tokens=40,
                ),
                timeout=timeout,
            )
            return json.loads(str(getattr(response, "output_text", "") or "")).get("grounded") is True
        except Exception:
            return False

    async def _catalog_answer_is_focused(
        self, *, question: str, answer: str, options: list[dict[str, str]], remaining: float | None,
    ) -> tuple[bool, str]:
        if self.client is None or (remaining is not None and remaining <= 5):
            return False, ""
        timeout = min(4.0, remaining - 2 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o-mini", store=False, tool_choice="none",
                    instructions=(
                        "Check whether the proposed answer respects the NUMBER and KIND of "
                        "indicator choices the user requested. If the user asks for one missing "
                        "indicator and why, a list of several catalog entries is not focused. "
                        "A broad request for several options may legitimately receive a list. "
                        "If the answer is unfocused, select exactly one of the supplied options "
                        "and mention it by its EXACT supplied display_name in "
                        "a brief replacement in the "
                        "question's language explaining its "
                        "general purpose. Do not assert a current reading, correlation or trade "
                        "conclusion. For a focused answer, leave selected_option and replacement empty."
                    ),
                    input=json.dumps({
                        "question": question, "answer": answer,
                        "supported_catalog_options": options,
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_catalog_answer_focus", "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "focused": {"type": "boolean"},
                                "selected_option": {"type": "string"},
                                "replacement": {"type": "string"},
                            },
                            "required": ["focused", "selected_option", "replacement"],
                        },
                    }},
                    max_output_tokens=180,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            if parsed.get("focused") is True:
                return True, ""
            selected = str(parsed.get("selected_option") or "")
            replacement = str(parsed.get("replacement") or "").strip()
            selected_option = next((
                option for option in options
                if selected.casefold() in {
                    str(option.get("name") or "").casefold(),
                    str(option.get("display_name") or "").casefold(),
                }
            ), None)

            def mentioned(option: dict[str, str]) -> bool:
                normalized_answer = re.sub(r"[^a-z0-9]", "", replacement.casefold())
                display = str(option.get("display_name") or "")
                labels = (
                    str(option.get("name") or ""), display,
                    display.split("(", 1)[0].strip(),
                )
                return any(
                    len(normalized_label) >= 3 and normalized_label in normalized_answer
                    for label in labels
                    if (normalized_label := re.sub(r"[^a-z0-9]", "", label.casefold()))
                )

            logger.info(
                "FINN catalog selection checked: known=%s mentioned=%s competing=%s",
                selected_option is not None,
                mentioned(selected_option) if selected_option else False,
                any(option is not selected_option and mentioned(option) for option in options),
            )
            if selected_option is None:
                return False, ""
            if not mentioned(selected_option):
                replacement = f"{selected_option.get('display_name') or selected_option.get('name')}: {replacement}"
            if any(
                option is not selected_option and mentioned(option)
                for option in options
            ):
                return False, ""
            return False, replacement
        except Exception:
            return False, ""

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
        clarification_calls = [
            call for call in result.tool_trace
            if call.get("name") == "ask_for_clarification" and call.get("status") == "needs_input"
        ]
        if clarification_calls:
            clarification = dict(clarification_calls[-1].get("result") or {})
            return FinnResponsesVerifiedAnswer(
                "clarification_required", str(clarification["question"]),
                str(clarification["reason"]), evidence,
                clarification={
                    "question": str(clarification["question"]),
                    "reason": str(clarification["reason"]),
                },
            )
        if any(item.get("reason") == "setup_ambiguous" for item in evidence) and not any(
            item.get("scope") == "read_active_setup" and item.get("status") == "completed"
            for item in evidence
        ):
            return FinnResponsesVerifiedAnswer(
                "clarification_required", self._fallback_copy("setup_ambiguous", message=message),
                "setup_ambiguous", evidence,
                clarification={
                    "question": self._fallback_copy("setup_ambiguous", message=message),
                    "reason": "setup_ambiguous",
                },
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
        direct_calls = [call for call in result.tool_trace if call.get("name") == "answer_directly"]
        if direct_calls and len(direct_calls) == len(result.tool_trace) and all(
            (call.get("arguments") or {}).get("uses_previous_response") is False
            for call in direct_calls
        ):
            previous_response = None
        previous_answer = str((previous_response or {}).get("answer") or "").strip()
        def quantities_supported(text: str) -> bool:
            return (
                self._amounts_supported(
                    answer=text, message=message, previous_answer=previous_answer,
                    evidence=evidence,
                )
                and self._asset_quantities_supported(
                    answer=text, message=message, evidence=evidence,
                )
                and self._currency_units_supported(
                    answer=text, message=message, evidence=evidence,
                )
                and not self._contains_internal_identifier(text)
            )
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
        reusing_previous_read = bool(previous_response and previous_response.get("answer")) and any(
            call.get("name") == "answer_directly"
            and dict(call.get("arguments") or {}).get("uses_previous_response") is True
            for call in result.tool_trace
        )
        current_scopes = {item.get("scope") for item in evidence}
        completed_scopes = {
            item.get("scope") for item in evidence if item.get("status") == "completed"
        }
        relevant_previous_source_evidence = [
            item for item in previous_source_evidence
            if item.get("scope") not in completed_scopes
            and (
                item.get("status") == "completed"
                or not current_scopes
                or item.get("scope") in current_scopes
            )
        ]
        compact.extend({
            "scope": item.get("scope"), "status": item.get("status"),
            "source": item.get("source"), "as_of": item.get("as_of"),
            "asset": item.get("asset"), "freshness": item.get("freshness"),
            "availability": item.get("availability"), "data": item.get("data"),
            "reason": item.get("reason"), "lineage": "previous_verified_run",
        } for item in relevant_previous_source_evidence if item.get("status") == "completed")
        unavailable_without_cause = any(
            item.get("reason") == "source_unavailable"
            for item in (*evidence, *relevant_previous_source_evidence)
        )
        limitation_only = bool(evidence) and all(item.get("status") != "completed" for item in evidence)
        missing_profile_established = any(
            item.get("scope") == "read_profile"
            and item.get("status") == "completed"
            and isinstance(item.get("data"), dict)
            and item["data"].get("has_profile") is False
            for item in evidence
        )
        profile_only = bool(evidence) and all(
            item.get("scope") in {"read_profile", "read_user_preferences"}
            for item in evidence
        )
        resolving_choice = message.startswith("Original user request:") and "User's chosen answer:" in message
        if previous_answer and not resolving_choice:
            compact.append({
                "scope": "previous_response",
                "source": "owner_scoped_runtime_contract",
                "availability": "available",
                "data": {
                    "answer": previous_answer,
                    "source_evidence": relevant_previous_source_evidence,
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
                "to that response, but reject invented causes, technical failures or unsupported advice. "
                "A saved setup or strategy proves its stored fields, not that those fields were "
                "derived from earlier analysis; reject an asserted analysis history unless the "
                "typed evidence contains it. "
                "For a short why follow-up, reject a mere recap of stored fields or a repetition "
                "of the same user question. Require an actual evidence-grounded explanation of "
                "the prior conclusion or why the previously requested detail is needed."
                " When a user asks for a personalized logical trading plan but the supplied "
                "evidence contains only saved profile/setup/strategy choices and no completed "
                "current market or owner-scoped risk evaluation, a short answer that names the "
                "verified saved settings, explicitly declines to judge suitability yet, and asks "
                "whether to perform the missing assessment IS a complete, safe answer. Do not "
                "fail it for not producing a trade recommendation; producing one would be unsafe. "
                " A stored entry, stop-loss, target or amount establishes only its configured value. "
                "It does not establish that the trade is prudent, profitable, realistic or suitable "
                "for this user. Reject those conclusions without current market and risk evidence. "
                "For example, an answer that turns a configured stop-loss into a recommendation to "
                "move it as prices rise, or calls a target logical or risk-controlled, is unsupported "
                "unless the supplied evidence proves that specific advice. A profile label and stored "
                "strategy fields alone are not enough. In particular, claiming that a saved setup "
                "is well aligned with the user's balanced risk profile or wealth-building goal "
                "requires an actual owner-scoped risk calculation or plan evaluation result, not "
                "just matching labels. Reject such a fit conclusion when that evidence is absent."
                " A completed owner-scoped read_profile with has_profile=false proves that profile "
                "goals and risk style are not saved. It supports a brief explanation that personal "
                "plan suitability cannot yet be assessed and a request for that user choice; it does "
                "not support inventing the missing profile or endorsing a trade. When the user asks "
                "what FINN can help with based on that absent profile, a factual statement of this "
                "limitation plus a request for the missing profile choice IS a complete, supported "
                "answer. Do not fail it merely because no personal recommendations are possible."
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
                "does not claim it is already saved. If the user asks which single indicator "
                "to consider next, enumerating the whole catalog does not answer the question. "
                "Require one supported, not-yet-configured choice with a short general reason "
                "and no unsupported current reading or market-effect claim."
                " A confirmed_action_result is verified persisted evidence of the object just saved. "
                "For a claim about which object was saved, its exact canonical_name must match this "
                "result; a short guided slot answer is not an object's name unless this result says so. "
                "Do not invent saved object names from conversation text. This action result proves "
                "only object identity and successful persistence, not its current asset, timeframe, "
                "frequency, amount, currency or other fields. Previous chat text and a draft are "
                "not a saved-object read. If an answer describes any such object fields, require a "
                "completed owner-scoped read of that object type in the current tool trace, "
                "or an immediately preceding verified owner-scoped read when answer_directly "
                "explicitly references that previous response and makes no new field claim; "
                "read_review_history and read_latest_report do not satisfy setup/strategy/bot "
                "field claims. Reject unsupported extra details even when the saved name is correct."
                " If the preceding response asked the user to choose a setup and the current "
                "read_active_setup result is completed for that chosen name, the choice is resolved. "
                "Reject an answer that asks the user to choose the same setup again; the answer "
                "must address the original request using the resolved evidence."
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
                    "For RSI, overbought and oversold describe momentum conditions; they do not "
                    "by themselves prove that an asset is objectively too expensive or too cheap. "
                    "Do not require any profile, plan, market or owner-scoped evidence for a general definition."
                    if general_education else ""
                )
        )
        mode = (
            "EXPLAIN" if (previous_answer and not resolving_choice) or general_education else
            "UNAVAILABLE" if limitation_only or (missing_profile_established and profile_only) else
            "READ"
        )
        user_message = (
            message if resolving_choice else
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
        if missing_profile_established:
            summary["missing_profile_established"] = True
        if resolving_choice:
            summary["permitted_limited_answer"] = (
                "Describe verified saved configuration, explicitly withhold any suitability "
                "judgment without a current market/risk evaluation, and offer that assessment."
            )
        personal_evidence = any(
            item.get("status") == "completed"
            and (
                item.get("scope") in {"read_active_setup", "read_linked_strategy"}
                or (
                    item.get("scope") == "read_profile"
                    and isinstance(item.get("data"), dict)
                    and item["data"].get("has_profile") is True
                )
            )
            for item in (*evidence, *(relevant_previous_source_evidence if reusing_previous_read else []))
        )
        unavailable_technical = any(
            item.get("scope") == "read_technical_snapshot"
            and item.get("status") != "completed"
            for item in evidence
        )
        advice_evidence = [
            item for item in compact
            if item.get("status") == "completed"
            and (
                item.get("lineage") != "previous_verified_run"
                or item.get("scope") == "read_profile"
                or reusing_previous_read
            )
        ]

        advice_cache: dict[str, bool] = {}
        technical_cache: dict[str, bool] = {}
        catalog_cache: dict[str, tuple[bool, str]] = {}
        catalog_options = [
            {"name": str(option.get("name") or ""),
             "display_name": str(option.get("display_name") or "")}
            for item in evidence if item.get("scope") == "available_macro_indicator_catalog"
            for option in (item.get("data") or {}).get("supported_options", [])
            if isinstance(option, dict)
        ]

        async def advice_supported(text: str) -> bool:
            if not personal_evidence or self.client is None:
                return True
            if text not in advice_cache:
                advice_cache[text] = await self._personal_advice_is_grounded(
                    answer=text, evidence=advice_evidence,
                    remaining=remaining_lifecycle_seconds(),
                    question=user_message if resolving_choice else None,
                )
            return advice_cache[text]

        async def technical_supported(text: str) -> bool:
            if not unavailable_technical:
                return True
            if text not in technical_cache:
                technical_cache[text] = await self._technical_limitation_is_grounded(
                    answer=text, remaining=remaining_lifecycle_seconds(),
                )
            return technical_cache[text]

        async def catalog_focused(text: str) -> bool:
            if not catalog_options:
                return True
            if text not in catalog_cache:
                catalog_cache[text] = await self._catalog_answer_is_focused(
                    question=user_message, answer=text, options=catalog_options,
                    remaining=remaining_lifecycle_seconds(),
                )
            return catalog_cache[text][0]

        async def verify_text(text: str):
            return await self.semantic.verify_async(
                mode=mode, user_message=user_message, mandatory=True,
                verification_guidance=guidance,
                sanitized_draft={"mode": mode, "direct_answer": text},
                compact_evidence=compact, deterministic_summary=summary,
            )

        verdict = await verify_text(result.text)
        advice_ok = await advice_supported(result.text) if verdict.available and (
            verdict.passes or resolving_choice
        ) else False
        technical_ok = await technical_supported(result.text) if verdict.available else False
        catalog_ok = await catalog_focused(result.text) if verdict.available else False
        verdict_passes = verdict.passes or (resolving_choice and personal_evidence and advice_ok)
        if verdict.available and not catalog_ok and catalog_options:
            focused_replacement = catalog_cache.get(result.text, (False, ""))[1]
            if focused_replacement:
                focused_verdict = await verify_text(focused_replacement)
                logger.info(
                    "FINN catalog focus repair checked: semantic=%s quantities=%s codes=%s",
                    focused_verdict.passes, quantities_supported(focused_replacement),
                    list(focused_verdict.reason_codes),
                )
                if (
                    focused_verdict.available and focused_verdict.passes
                    and quantities_supported(focused_replacement)
                    and await advice_supported(focused_replacement)
                    and await technical_supported(focused_replacement)
                ):
                    return FinnResponsesVerifiedAnswer(
                        "completed", focused_replacement, None, evidence, bool(previous_answer),
                    )
            else:
                logger.info("FINN catalog focus repair produced no valid single-option answer")
        if not verdict.available or not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok:
            logger.info(
                "FINN Responses answer verification rejected draft: codes=%s available=%s semantic_pass=%s quantities=%s",
                list(verdict.reason_codes), verdict.available, verdict.passes,
                quantities_supported(result.text),
                extra={
                    "stage": "responses_answer_verifier",
                    "reason_codes": list(verdict.reason_codes),
                    "semantic_available": verdict.available,
                    "semantic_passes": verdict.passes,
                    "quantities_supported": quantities_supported(result.text),
                    "evidence_scopes": [item.get("scope") for item in evidence],
                },
            )
        if verdict.available and verdict.passes and quantities_supported(result.text) and previous_answer and unavailable_without_cause:
            if not await self._cause_claim_is_grounded(
                answer=result.text, remaining=remaining_lifecycle_seconds(),
            ):
                return FinnResponsesVerifiedAnswer(
                    "unavailable",
                    self._fallback_copy("previous_source_unavailable", message=message, previous_answer=previous_answer),
                    "source_unavailable", evidence, True,
                )
        if verdict.available and (not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok) and self.client is not None:
            remaining = remaining_lifecycle_seconds()
            if remaining is None or remaining > 8:
                try:
                    response = await asyncio.wait_for(
                        self.client.responses.create(
                            model="gpt-4o-mini", store=False,
                            instructions=(
                                "You are FINN. Rewrite the answer in the user's language using ONLY the "
                                "typed evidence and previous verified answer provided. The prior draft was "
                                "rejected as unsupported and is intentionally not supplied. Do not attach "
                                "a currency or asset unit to a bare numeric field; base_amount=100 does not "
                                "mean 100 BTC, $100 or €100 without explicit currency evidence. "
                                "State unavailable data and unknown causes plainly; "
                                "For unavailable technical indicators, never suggest a temporary outage "
                                "and check educational facts: RSI below 30 is commonly oversold, not overbought. "
                                "Do not equate overbought or oversold with proof that an asset is "
                                "objectively too expensive or too cheap. "
                                "do not invent prices, user facts, recommendations or provider failures. "
                                "Never print database IDs, even when they appear in evidence. "
                                "Do not replace an explicit action request with a read-only answer; "
                                "without a proposal tool result, do not claim the action was prepared. "
                                "A saved strategy and profile establish their stored values only. "
                                "A completed read_active_setup or read_linked_strategy result means "
                                "those saved fields ARE available; do not say you cannot access them "
                                "or ask the user to repeat them. If the original request asked for a "
                                "plan and the chosen setup was resolved, do not repeat the earlier "
                                "setup-choice question. "
                                "If the user asks for one missing indicator, choose at most one "
                                "supported unsaved catalog option with a short general reason; "
                                "never dump the catalog. "
                                "Without a current owner-scoped risk or market evaluation, do not say "
                                "that this strategy fits the user's goals or risk style. Instead, "
                                "describe the saved settings accurately and say what assessment is "
                                "still missing before judging suitability. For a short why follow-up, "
                                "explain the prior statement without inventing historical market "
                                "conditions or recommending a level change. "
                                + (
                                    "The prior answer failed the personal-advice audit. Write two or "
                                    "three plain sentences: identify the verified saved settings; "
                                    "explicitly say that no current market/risk assessment has been "
                                    "performed, so suitability is not yet established; optionally "
                                    "ask whether the user wants that assessment. Do not present a "
                                    "trading-plan checklist, prescribe levels, or suggest that the "
                                    "saved strategy helps achieve an investment goal. "
                                    if not advice_ok else ""
                                )
                                + "Keep it brief and natural. Never expose internal IDs or reason codes."
                            ),
                            input=json.dumps({
                                "question": user_message, "evidence": compact,
                                "rejection_reasons": list(verdict.reason_codes)
                                + (["personal_advice_not_grounded"] if not advice_ok else [])
                                + (["technical_claim_not_grounded"] if not technical_ok else [])
                                + (["catalog_answer_not_focused"] if not catalog_ok else []),
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
                        revised_advice_ok = await advice_supported(revised) if revised_verdict.available and (
                            revised_verdict.passes or resolving_choice
                        ) else False
                        revised_technical_ok = await technical_supported(revised) if revised_verdict.available else False
                        revised_catalog_ok = await catalog_focused(revised) if revised_verdict.available else False
                        revised_passes = revised_verdict.passes or (
                            resolving_choice and personal_evidence and revised_advice_ok
                        )
                        if revised_verdict.available and revised_passes and quantities_supported(revised):
                            if not revised_advice_ok or not revised_technical_ok or not revised_catalog_ok:
                                return FinnResponsesVerifiedAnswer(
                                    "unavailable",
                                    self._fallback_copy("responses_evidence_not_verified", message=message, previous_answer=previous_answer),
                                    "responses_evidence_not_verified", evidence, bool(previous_answer),
                                )
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
        if not verdict.available or not verdict_passes or not quantities_supported(result.text) or not advice_ok or not technical_ok or not catalog_ok:
            reason = (
                "responses_evidence_not_verified"
                if not quantities_supported(result.text)
                else self._typed_failure_reason((*evidence, *relevant_previous_source_evidence))
            )
            answer = self._fallback_copy(
                "previous_source_unavailable" if previous_answer and unavailable_without_cause else reason,
                message=message, previous_answer=previous_answer,
            )
            return FinnResponsesVerifiedAnswer(
                "unavailable", answer, reason, evidence, bool(previous_answer),
            )
        return FinnResponsesVerifiedAnswer("completed", result.text, None, evidence, bool(previous_answer))
