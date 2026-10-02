"""Narrow evidence boundary for model-written FINN answers.

The extractor identifies assertions; only typed FINN results decide whether
those assertions may be shown. It never chooses a tool or writes coach copy.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import json
import os
import re
from typing import Any

from backend.utils.openai_client import StructuredOutputSpec, ask_gpt_structured_response_async


_CLAIM_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "personal_fit_quote": {"type": "string"},
        "current_market_quote": {"type": "string"},
        "claimed_saved_action_quote": {"type": "string"},
        "outcome_claim_quote": {"type": "string"},
        "condition_bypass_quote": {"type": "string"},
    },
    "required": [
        "personal_fit_quote", "current_market_quote", "claimed_saved_action_quote",
        "outcome_claim_quote", "condition_bypass_quote",
    ],
}

_CONDITION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommends_entry_before_condition": {"type": "boolean"},
        "violating_quote": {"type": "string"},
    },
    "required": ["recommends_entry_before_condition", "violating_quote"],
}

_WHOLE_ANSWER_FIT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "asserts_personal_fit": {"type": "boolean"},
        "violating_quote": {"type": "string"},
    },
    "required": ["asserts_personal_fit", "violating_quote"],
}

_WHOLE_ANSWER_FIT_MODEL = os.getenv("FINN_RESPONSES_FIT_CHECK_MODEL") or "gpt-6-luna"

_OUTCOME_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {"predicts_user_outcome": {"type": "boolean"}},
    "required": ["predicts_user_outcome"],
}

_CLAIM_INSTRUCTIONS = (
    "Extract exact claims from the assistant answer. personal_fit_quote is the shortest "
    "verbatim span asserting or implying that this user's saved plan, setup, strategy, "
    "asset or trading method suits their risk style, goals or circumstances. Include "
    "partial or hedged positive fit claims, but only when the answer actually "
    "asserts compatibility, suitability, or recommends the specific plan or amount. "
    "A sentence merely stating the user's risk style and mentioning their method "
    "does not assert that the method fits that style. An explicit statement that fit "
    "cannot be established is not a positive fit claim. A general statement about a method "
    "and a broad risk category is educational, not a claim that this particular "
    "user's saved setup or proposed amount fits them. Do not infer a personal "
    "assertion only from the user's question; extract only what the answer asserts. "
    "current_market_quote is an exact span asserting a present market price, trend or "
    "indicator reading. claimed_saved_action_quote is an exact span asserting "
    "that FINN just saved, changed, deleted or executed an action in this turn. "
    "Describing a pre-existing saved profile, setup or strategy found by a read "
    "is a state claim, not a claim that FINN executed a new action. "
    "outcome_claim_quote is an exact span predicting "
    "this user's actual or expected profit, loss, success rate or investment risk "
    "from a trading method, including hedged promises. A general explanation of "
    "how purchase frequency changes timing concentration or price averaging is "
    "method mechanics, not a prediction of this user's trading outcome. Use an "
    "empty string when a category is absent. "
    "condition_bypass_quote is an exact span of the assistant answer suggesting "
    "opening or increasing a position, or placing an order that could execute, before "
    "a prerequisite the user says must be met, even as a smaller or partial position. "
    "This includes a limit order placed while waiting for confirmation unless the "
    "answer explicitly conditions order placement on confirmation first. "
    "A sentence that negates bypassing "
    "the rule (for example 'you do not need to ignore the wait rule') is NOT "
    "a bypass claim. Do not mark advice to wait for the prerequisite, or a "
    "discussion of the user's fear, as a bypass. Use the "
    "user_message only to identify the stated prerequisite, never as proof it is saved. "
    "Do not judge writing style, helpfulness or what the assistant should say."
)


@dataclass(frozen=True)
class HardClaimBoundaryResult:
    available: bool
    violations: tuple[str, ...]
    quotes: dict[str, str]


class FinnV2HardClaimBoundary:
    @staticmethod
    def _read_only_saved_action_quote(quote: str) -> bool:
        """A quoted lookup is not a claim that FINN changed saved state."""
        return bool(re.search(
            r"\b(?:opgezocht|gelezen|geraadpleegd|ingelezen|looked up|read|consulted|"
            r"nachgeschlagen|gelesen)\b", quote, re.I,
        )) and not bool(re.search(
            r"\b(?:gewijzigd|veranderd|aangepast|opgeslagen|verwijderd|aangemaakt|"
            r"toegevoegd|uitgevoerd|changed|modified|saved|deleted|created|added|"
            r"executed|geändert|gespeichert|gelöscht|erstellt|hinzugefügt|ausgeführt)\b",
            quote, re.I,
        ))

    @staticmethod
    def _negated_saved_action(answer: str, quote: str) -> bool:
        """A denial of a write is not evidence that FINN performed one."""
        position = answer.casefold().find(quote.casefold())
        if position < 0:
            return False
        clause = re.split(r"[.!?;\n]", answer[:position + len(quote)])[-1]
        if re.search(r"\b(?:niet alleen|not only|nicht nur)\b", clause, re.I):
            return False
        return bool(re.search(
            r"\b(?:niets|niet|geen|nothing|not|no|kein\w*|nichts|nicht)\b"
            r"[^.!?;\n]{0,35}\b(?:gewijzigd|veranderd|aangepast|opgeslagen|verwijderd|"
            r"changed|modified|saved|deleted|geändert|gespeichert|gelöscht)\b",
            clause, re.I,
        ))

    @staticmethod
    def _negated_outcome_assessment(answer: str, quote: str) -> bool:
        """A denial of evidence for an outcome is not an outcome prediction."""
        position = answer.casefold().find(quote.casefold())
        if position < 0:
            return False
        clause = re.split(
            r"[.!?;\n]|\b(?:maar|but|aber)\b",
            answer[:position + len(quote)], flags=re.I,
        )[-1]
        return bool(re.search(
            r"\b(?:geen\s+(?:bewijs|beoordeling|inschatting|uitspraak)|"
            r"niet\s+(?:beoordelen|vaststellen|inschatten)|"
            r"no\s+(?:evidence|proof|assessment|estimate)|"
            r"not\s+(?:an?\s+)?(?:assessment|estimate|evidence)|"
            r"cannot\s+(?:assess|establish|estimate)|"
            r"kein\w*\s+(?:Beweis|Bewertung|Einschätzung))\b",
            clause, re.I,
        ))

    @classmethod
    def _saved_state_readback(cls, quote: str, tool_trace: tuple[dict[str, Any], ...]) -> bool:
        """A stored-object description is not a claim of a new write."""
        existing_state = (
            re.search(r"\b(?:opgeslagen|saved|gespeichert)\s+(?:[\w]+[-\s]+){0,3}(?:setup|plan|profiel|profile|strategie|strategy|opzet|instelling|setting)\b", quote, re.I)
            or re.search(r"\b(?:setup|plan|profiel|profile|strategie|strategy|opzet|instelling|setting)\b[^.!?]{0,90}\b(?:is|was|ist|are|were)\s+(?:opgeslagen|saved|gespeichert)\b", quote, re.I)
            or re.search(r"\b(?:is|was|ist|are|were)\b[^.!?]{0,100}\b(?:setup|plan|profiel|profile|strategie|strategy|opzet|instelling|setting)\b[^.!?]{0,90}\b(?:opgeslagen|saved|gespeichert)\b", quote, re.I)
            or re.search(r"\b(?:je|jij)\b[^.!?]{0,90}\b(?:setup|plan|profiel|strategie|instelling)\b[^.!?]{0,50}\b(?:hebt|had)\s+opgeslagen\b", quote, re.I)
        )
        if not existing_state:
            return False
        if re.search(r"\b(?:zojuist|net|just|gerade|now|nu|eben|soeben|aangepast|changed|geändert|deleted|verwijderd|gelöscht)\b", quote, re.I):
            return False
        return any(
            item.get("status") == "completed"
            and item.get("scope") in {"read_profile", "read_active_setup", "read_linked_strategy"}
            for item in cls._typed_results(tool_trace)
        )

    @staticmethod
    def _typed_results(tool_trace: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
        return tuple(
            item
            for call in tool_trace
            for item in (call.get("result") or {}).get("results") or []
            if isinstance(item, dict)
        )

    @classmethod
    def _supported_claims(
        cls, tool_trace: tuple[dict[str, Any], ...],
        recent_action_result: dict[str, Any] | None,
    ) -> dict[str, bool]:
        results = cls._typed_results(tool_trace)
        return {
            "personal_fit_quote": any(
                (call.get("result") or {}).get("evidence_coverage", {})
                .get("full_assessment", {}).get("status") == "available"
                and bool((call.get("result") or {}).get("evaluation_operation_id"))
                for call in tool_trace
            ),
            "current_market_quote": any(
                item.get("status") == "completed"
                and item.get("scope") in {
                    "read_market_snapshot", "read_macro_snapshot", "read_technical_snapshot",
                }
                and item.get("freshness") == "fresh"
                and bool(item.get("as_of"))
                for item in results
            ),
            "claimed_saved_action_quote": bool(
                recent_action_result
                and recent_action_result.get("result_status") in {"succeeded", "already_executed"}
                and recent_action_result.get("execution_id")
            ),
            "outcome_claim_quote": any(
                (call.get("result") or {}).get("outcome_evidence_status") == "verified"
                for call in tool_trace
            ),
            "condition_bypass_quote": False,
        }

    @classmethod
    def repair_evidence(
        cls, tool_trace: tuple[dict[str, Any], ...],
        recent_action_result: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Project only typed source facts needed to retract an unsupported claim."""
        factual_scopes = {
            "read_profile", "read_active_setup", "read_linked_strategy",
            "read_market_snapshot", "read_macro_snapshot", "read_technical_snapshot",
        }
        facts = []
        for item in cls._typed_results(tool_trace):
            scope = item.get("scope")
            if scope not in factual_scopes:
                continue
            source = {
                key: item.get(key)
                for key in ("scope", "status", "source", "as_of", "freshness", "asset", "reason")
                if item.get(key) is not None
            }
            if item.get("status") == "completed" and isinstance(item.get("data"), dict):
                data = item["data"]
                if scope == "read_profile":
                    source["data"] = {
                        "has_profile": data.get("has_profile"),
                        "risk_profiles": (data.get("trader_profile") or {}).get("risk_profiles"),
                        "investment_goals": (data.get("trader_profile") or {}).get("investment_goals"),
                    }
                elif scope == "read_active_setup":
                    saved = data.get("fields") if isinstance(data.get("fields"), dict) else data
                    source["data"] = {
                        key: saved[key] for key in (
                            "name", "symbol", "timeframe", "setup_type", "dca_frequency",
                        ) if saved.get(key) is not None
                    }
                elif scope == "read_linked_strategy":
                    source["data"] = {
                        key: data[key] for key in (
                            "name", "strategy_name", "symbol", "timeframe", "execution_mode",
                            "base_amount", "entry", "stop_loss", "targets", "risk_profile",
                        ) if data.get(key) is not None
                    }
                else:
                    source["data"] = data
            facts.append(source)
        assessments = [
            {
                "operation_id": result.get("evaluation_operation_id"),
                "assessment_status": result.get("assessment_status"),
                "missing_required_scopes": result.get("missing_required_scopes") or [],
            }
            for call in tool_trace
            for result in (call.get("result") or {},)
            if result.get("evaluation_operation_id")
        ]
        return {
            "claim_support": cls._supported_claims(tool_trace, recent_action_result),
            "assessments": assessments,
            "source_facts": facts,
        }

    async def assess(
        self, *, answer: str, tool_trace: tuple[dict[str, Any], ...],
        recent_action_result: dict[str, Any] | None = None,
        user_message: str = "",
    ) -> HardClaimBoundaryResult:
        quotes: dict[str, str] = {}
        condition_check = None
        whole_answer_fit_check = None
        for attempt in range(2):
            instructions = _CLAIM_INSTRUCTIONS
            if attempt:
                instructions += (
                    " The previous extraction did not quote the answer verbatim. "
                    "Recheck the answer. Every nonempty quote MUST be a contiguous exact "
                    "substring of the answer, including its original punctuation and spacing. "
                    "If no exact substring supports a category, return an empty string."
                )
            extraction = ask_gpt_structured_response_async(
                prompt=json.dumps({"answer": answer, "user_message": user_message}, ensure_ascii=False),
                system_role=instructions,
                output_spec=StructuredOutputSpec(name="finn_v2_hard_claims", schema=_CLAIM_SCHEMA),
                model_override="gpt-4o-mini", timeout_seconds=15, client_max_retries=0,
            )
            if not attempt:
                response, condition_check, whole_answer_fit_check = await asyncio.gather(
                    extraction,
                    ask_gpt_structured_response_async(
                        prompt=json.dumps(
                            {"user_message": user_message, "assistant_answer": answer},
                            ensure_ascii=False,
                        ),
                        system_role=(
                            "Check whether the assistant recommends placing an executable order "
                            "or taking a position before a user-stated confirmation prerequisite. "
                            "A limit order suggested during the wait can execute before confirmation. "
                            "If true, violating_quote must be the shortest contiguous exact "
                            "substring of assistant_answer that recommends the order or position. "
                            "If false, violating_quote must be empty."
                        ),
                        output_spec=StructuredOutputSpec(
                            name="finn_v2_condition_bypass_check", schema=_CONDITION_SCHEMA,
                        ),
                        model_override="gpt-4o-mini", timeout_seconds=15,
                        client_max_retries=0,
                    ),
                    ask_gpt_structured_response_async(
                        prompt=json.dumps({"assistant_answer": answer}, ensure_ascii=False),
                        system_role=(
                            "Does the assistant answer assert that this specific user's "
                            "investment setup, trading strategy, asset, method or proposed "
                            "amount is suitable, compatible or manageable for their personal "
                            "risk style, goals or finances? "
                            "A hedged positive assessment such as 'could fit' or 'broadly fits' "
                            "is TRUE even when a later sentence says a complete assessment is "
                            "not possible. Judge the positive clause, not the overall tone. "
                            "Advice to respect a self-imposed prerequisite or avoid an "
                            "impulsive trade is process guidance, not a suitability assessment "
                            "of the user's investment setup, even when the answer mentions "
                            "a saved risk profile or goal. "
                            "A statement that suitability cannot be established, or a "
                            "general educational explanation of a method, is FALSE. "
                            "If true, quote the shortest contiguous exact span from the "
                            "assistant answer that makes the positive assessment. If false, "
                            "return an empty quote."
                        ),
                        output_spec=StructuredOutputSpec(
                            name="finn_v2_whole_answer_personal_fit_check",
                            schema=_WHOLE_ANSWER_FIT_SCHEMA,
                        ),
                        model_override=_WHOLE_ANSWER_FIT_MODEL, timeout_seconds=15,
                        reasoning_effort=(
                            "none" if _WHOLE_ANSWER_FIT_MODEL == "gpt-6-luna" else None
                        ),
                        client_max_retries=0,
                    ),
                )
            else:
                response = await extraction
            if response.get("error") or not isinstance(response.get("parsed"), dict):
                return HardClaimBoundaryResult(False, ("claim_extraction_unavailable",), {})
            parsed = response["parsed"]
            quotes = {key: str(parsed.get(key) or "").strip() for key in _CLAIM_SCHEMA["required"]}
            if all(not quote or quote.casefold() in answer.casefold() for quote in quotes.values()):
                break
        else:
            return HardClaimBoundaryResult(True, ("claim_quote_invalid",), quotes)
        parsed_whole_fit = (whole_answer_fit_check or {}).get("parsed")
        if (whole_answer_fit_check or {}).get("error") or not isinstance(parsed_whole_fit, dict) or not isinstance(
            parsed_whole_fit.get("asserts_personal_fit"), bool,
        ) or not isinstance(parsed_whole_fit.get("violating_quote"), str):
            return HardClaimBoundaryResult(False, ("personal_fit_check_unavailable",), quotes)
        unquoted_personal_fit = False
        if parsed_whole_fit["asserts_personal_fit"]:
            quote = parsed_whole_fit["violating_quote"].strip()
            if not quote or quote.casefold() not in answer.casefold():
                unquoted_personal_fit = True
            else:
                quotes["personal_fit_quote"] = quote
        else:
            quotes["personal_fit_quote"] = ""
        if quotes["outcome_claim_quote"] and self._negated_outcome_assessment(
            answer, quotes["outcome_claim_quote"],
        ):
            quotes["outcome_claim_quote"] = ""
        if quotes["outcome_claim_quote"]:
            outcome_check = await ask_gpt_structured_response_async(
                prompt=json.dumps(
                    {"quoted_claim": quotes["outcome_claim_quote"]}, ensure_ascii=False,
                ),
                system_role=(
                    "Does this quote predict the user's actual or expected profit, loss, "
                    "success rate or total investment risk? General explanations of "
                    "purchase frequency, timing concentration, price averaging or "
                    "volatility exposure without a predicted user outcome are FALSE. "
                    "A hedged promise of better returns or fewer losses is TRUE."
                ),
                output_spec=StructuredOutputSpec(
                    name="finn_v2_outcome_check", schema=_OUTCOME_SCHEMA,
                ),
                model_override="gpt-4o-mini", timeout_seconds=15, client_max_retries=0,
            )
            parsed_outcome = outcome_check.get("parsed")
            if outcome_check.get("error") or not isinstance(parsed_outcome, dict) or not isinstance(
                parsed_outcome.get("predicts_user_outcome"), bool,
            ):
                return HardClaimBoundaryResult(False, ("outcome_check_unavailable",), quotes)
            if not parsed_outcome["predicts_user_outcome"]:
                quotes["outcome_claim_quote"] = ""
        parsed_check = (condition_check or {}).get("parsed")
        if (condition_check or {}).get("error") or not isinstance(parsed_check, dict) or not isinstance(
            parsed_check.get("recommends_entry_before_condition"), bool,
        ) or not isinstance(parsed_check.get("violating_quote"), str):
            return HardClaimBoundaryResult(False, ("condition_check_unavailable",), quotes)
        if parsed_check["recommends_entry_before_condition"]:
            quote = parsed_check["violating_quote"].strip()
            if not quote or quote.casefold() not in answer.casefold():
                return HardClaimBoundaryResult(False, ("condition_quote_invalid",), quotes)
            quotes["condition_bypass_quote"] = quote
        else:
            quotes["condition_bypass_quote"] = ""
        supported = self._supported_claims(tool_trace, recent_action_result)
        if quotes["claimed_saved_action_quote"] and self._negated_saved_action(
            answer, quotes["claimed_saved_action_quote"],
        ):
            quotes["claimed_saved_action_quote"] = ""
        if quotes["claimed_saved_action_quote"] and self._read_only_saved_action_quote(
            quotes["claimed_saved_action_quote"],
        ):
            quotes["claimed_saved_action_quote"] = ""
        if self._saved_state_readback(quotes["claimed_saved_action_quote"], tool_trace):
            quotes["claimed_saved_action_quote"] = ""
        violations = tuple(
            key.removesuffix("_quote")
            for key, quote in quotes.items()
            if quote and not supported[key]
        )
        if unquoted_personal_fit and not supported["personal_fit_quote"]:
            violations = tuple(dict.fromkeys((*violations, "personal_fit")))
        return HardClaimBoundaryResult(True, violations, quotes)
