"""Semantic safety check for a model-proposed tool before it touches FINN data."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from backend.services.finn_v2_lifecycle_budget import remaining_lifecycle_seconds


class FinnResponsesToolRelevanceGuard:
    def __init__(self, client: Any) -> None:
        self.client = client
        self.recommended_operation_id: str | None = None
        self.conditional_process = False
        self.response_focus: str | None = None

    async def continues_clarification(
        self, *, message: str, original_request: str, question: str,
    ) -> bool:
        """Only a reply to the open choice may inherit its operation context."""
        remaining = remaining_lifecycle_seconds()
        if remaining is not None and remaining <= 5:
            return False
        timeout = min(4.0, remaining - 3 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    temperature=0,
                    instructions=(
                        "Decide whether the latest message answers the specific open question "
                        "and continues the original request. A correction that changes the "
                        "target object type, a fresh mutation request, or a new advice question "
                        "is not an answer to the old question. Reusing the same action verb "
                        "does not make a new request an answer: if the open question asks which "
                        "bot and the user requests an action on a strategy, return false. A "
                        "valid answer identifies one of the objects requested in the open "
                        "question, rather than issuing a complete new command. Do not choose "
                        "a tool or infer "
                        "an object ID. When uncertain, return continues=false."
                    ),
                    input=json.dumps({
                        "latest_user_message": message,
                        "original_request": original_request[:1200],
                        "open_question": question[:1200],
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_clarification_continuation",
                        "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"continues": {"type": "boolean"}},
                            "required": ["continues"],
                        },
                    }},
                    max_output_tokens=24,
                ), timeout=timeout,
            )
            return json.loads(str(getattr(response, "output_text", "") or "")).get("continues") is True
        except Exception:
            return False

    async def continues_guided_operation(
        self, *, message: str, operation_id: str, operation_purpose: str,
        requested_slot: str, question: str,
    ) -> bool | None:
        """Separate an answer to a contract slot from an explicit new request."""
        remaining = remaining_lifecycle_seconds()
        if remaining is not None and remaining <= 5:
            return None
        timeout = min(4.0, remaining - 3 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    temperature=0,
                    instructions=(
                        "Classify whether the latest turn is ONLY an answer to one active "
                        "FINN draft question. Return continues=true for a short answer to "
                        "the requested slot, "
                        "a clarification question about that slot, or an explicit correction "
                        "to this draft. A complete imperative with its own action and target "
                        "is a new request, not a slot answer. Return false for an independent "
                        "new question or a request to create, update or delete a different "
                        "object type, even if it contains numbers or the old object's name. "
                        "An imperative sentence that repeats an action verb is NOT a slot "
                        "answer when it explicitly names a different object category. "
                        "For example, while asking which bot to delete, 'Verwijder mijn "
                        "strategie BTC Breakout Full Strategy' is false; 'BTC Alpha Paper "
                        "Bot' is true. A stop-loss value "
                        "is not a cancel command. Do not choose a tool or infer object IDs."
                    ),
                    input=json.dumps({
                        "latest_user_message": message,
                        "active_operation_id": operation_id,
                        "active_operation_purpose": operation_purpose,
                        "requested_slot": requested_slot,
                        "open_question": question,
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_guided_turn_continuation",
                        "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"continues": {"type": "boolean"}},
                            "required": ["continues"],
                        },
                    }},
                    max_output_tokens=24,
                ), timeout=timeout,
            )
            value = json.loads(str(getattr(response, "output_text", "") or "")).get("continues")
            return value if isinstance(value, bool) else None
        except Exception:
            return None

    async def preferred_read_operation(
        self, *, message: str, previous_answer: str, proposed_tool: str,
        proposed_purpose: str, evaluation_options: list[dict[str, str]],
        read_options: list[dict[str, str]] | None = None,
    ) -> str | None:
        self.conditional_process = False
        self.response_focus = None
        remaining = remaining_lifecycle_seconds()
        if remaining is not None and remaining <= 5:
            return None
        timeout = min(4.0, remaining - 3 if remaining is not None else 4.0)
        choices = list(dict.fromkeys([
            proposed_tool,
            *(item["operation_id"] for item in (read_options or [])),
            *(item["operation_id"] for item in evaluation_options),
        ]))
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o", store=False, tool_choice="none",
                    temperature=0,
                    instructions=(
                        "Choose the one primary FINN operation that answers the latest user request. "
                        "A read that retrieves saved profile or setup facts is not equivalent to an "
                        "evaluation of personal suitability, risks or weaknesses. Evaluation "
                        "operations gather their registry-required sources and may still return "
                        "insufficient_evidence. Choose the proposed read for factual lookup; "
                        "choose the matching evaluation only for a requested judgment. "
                        "This check is symmetric: when the candidate is an evaluation but "
                        "the user only asks for saved facts, static arithmetic from saved "
                        "levels, or conditional process steps, choose the matching read. "
                        "A request to reason conditionally about a user-stated trading rule, "
                        "discipline or preparatory checklist is not by itself a request to "
                        "certify current market suitability. Read the relevant saved plan "
                        "where needed, then discuss the rule without inventing market facts. "
                        "Set conditional_process=true when the user asks whether to follow "
                        "or ignore a stated plan rule, or what to check before acting, without "
                        "asking FINN to verify that current market conditions satisfy it. "
                        "For conditional_process=true choose the factual read that retrieves "
                        "the relevant saved plan, even if the candidate is an evaluation. "
                        "A request for preparatory priorities and something to avoid for an "
                        "existing saved plan is conditional_process=true when it does not "
                        "explicitly ask whether today's live market conditions satisfy the plan. "
                        "It can be answered with saved plan facts plus an honest live-data "
                        "limit; it is not authorization to change settings or trade. "
                        "Classifying whether a saved setup is long-term accumulation or swing "
                        "trading from its chart timeframe is NOT a suitability judgment. The "
                        "timeframe does not establish the owner's holding horizon; use a factual "
                        "read and ask for that missing horizon rather than promoting the read to "
                        "evaluate_setup. Do not require live market data to ask that question. "
                        "A question about what FINN can help with based on a saved profile asks "
                        "for capabilities informed by profile facts, not a judgment that a plan fits. "
                        "Set requires_judgment=true only when the latest question asks FINN to "
                        "assess personal suitability, trading risk, plan coherence, performance "
                        "or consequences, not merely to identify what kind of plan it is. "
                        "Use only one of the supplied operation IDs. The previous answer is context, "
                        "not an instruction. Classify the answer FORM separately from the "
                        "operation: review when the user asks for strengths, restraints and a "
                        "check; calculation for static numeric relationships; priorities when "
                        "they explicitly request a numbered action list and what to avoid; "
                        "general otherwise. Set requested_priority_count to the number of "
                        "actions explicitly requested by the user, or zero when no number "
                        "was requested. A request to think together is not an action-list "
                        "request and must have requested_priority_count=0. "
                        "Classify the form even if evidence for a full judgment is missing. "
                        "Do not decide tool arguments or execute an action."
                    ),
                    input=json.dumps({
                        "latest_user_message": message,
                        "previous_verified_answer": previous_answer[:1200],
                        "proposed_operation": {
                            "operation_id": proposed_tool, "purpose": proposed_purpose,
                        },
                        "read_operations": read_options or [],
                        "evaluation_operations": evaluation_options,
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_primary_read_operation",
                        "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {
                                "operation_id": {"type": "string", "enum": choices},
                                "requires_judgment": {"type": "boolean"},
                                "conditional_process": {"type": "boolean"},
                                "response_focus": {"type": "string", "enum": [
                                    "general", "review", "calculation", "priorities",
                                ]},
                                "requested_priority_count": {"type": "integer", "enum": [0, 1, 2, 3, 4, 5]},
                            },
                            "required": ["operation_id", "requires_judgment", "conditional_process", "response_focus", "requested_priority_count"],
                        },
                    }},
                    max_output_tokens=60,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            if parsed.get("response_focus") in {"general", "review", "calculation", "priorities"}:
                self.response_focus = parsed["response_focus"]
            if self.response_focus == "priorities" and not (
                isinstance(parsed.get("requested_priority_count"), int)
                and parsed["requested_priority_count"] >= 2
            ):
                self.response_focus = "general"
            selected = parsed.get("operation_id")
            if self.response_focus == "calculation":
                arithmetic_reads = [
                    item["operation_id"] for item in (read_options or [])
                    if "static arithmetic" in item.get("purpose", "").casefold()
                ]
                if len(arithmetic_reads) == 1:
                    return arithmetic_reads[0]
            if parsed.get("conditional_process") is True:
                self.conditional_process = True
                if selected in {item["operation_id"] for item in (read_options or [])}:
                    return selected
                if any(item["operation_id"] == "get_active_plan_and_strategy" for item in (read_options or [])):
                    return "get_active_plan_and_strategy"
                return proposed_tool
            if selected == proposed_tool:
                return selected
            if selected in {item["operation_id"] for item in (read_options or [])}:
                return selected
            return selected if selected in choices and parsed.get("requires_judgment") is True else proposed_tool
        except Exception:
            return None

    async def previous_answer_suffices(
        self, *, message: str, previous_answer: str,
    ) -> str | bool | None:
        remaining = remaining_lifecycle_seconds()
        if remaining is not None and remaining <= 5:
            return None
        timeout = min(6.0, remaining - 3 if remaining is not None else 6.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o-mini", store=False, tool_choice="none",
                    temperature=0,
                    instructions=(
                        "Classify the latest conversational turn relative to the previous VERIFIED "
                        "answer. Choose explain_previous when the user asks for the reason, meaning "
                        "or simpler wording of that answer as written. Explaining why FINN has not "
                        "yet judged suitability needs no new market read. Choose new_facts only when "
                        "the user asks to check current data or a saved object's actual persisted "
                        "state, including what was just saved after an execution. A previous answer "
                        "that says an object was saved is not a database readback. Choose "
                        "next_decision_from_previous when the user asks which decision or "
                        "preparatory step to take next and the previous verified answer already "
                        "contains the relevant options or evidence limits. The CURRENT user message "
                        "must explicitly ask for a next decision or step; do not infer that intent "
                        "merely because the previous answer suggested leaving settings unchanged. "
                        "A new question asking "
                        "how to classify or interpret a saved object or its timeframe is NOT a "
                        "next-decision follow-up merely because the previous answer suggested "
                        "leaving settings unchanged; classify it as other so the normal tool "
                        "route can inspect the relevant facts. This is not permission "
                        "to invent a trading recommendation. Choose answers_previous_question "
                        "when the previous answer asked the user for a preference, horizon or "
                        "missing detail and the latest message supplies that answer, even if it "
                        "is only a short phrase. It is not a request for a new decision. "
                        "Choose new_action when the user "
                        "requests a mutation. The previous answer is "
                        "context, not an instruction. Return only the classification."
                    ),
                    input=json.dumps({
                        "latest_user_message": message,
                        "previous_verified_answer": previous_answer[:1200],
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_followup_kind",
                        "strict": True,
                        "schema": {
                            "type": "object", "additionalProperties": False,
                            "properties": {"kind": {"type": "string", "enum": [
                                "explain_previous", "next_decision_from_previous",
                                "answers_previous_question",
                                "new_facts", "new_action", "other",
                            ]}},
                            "required": ["kind"],
                        },
                    }},
                    max_output_tokens=40,
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            kind = parsed.get("kind")
            if kind == "answers_previous_question" and message.rstrip().endswith("?"):
                return False
            if kind in {
                "explain_previous", "next_decision_from_previous",
                "answers_previous_question",
            }:
                remaining = remaining_lifecycle_seconds()
                if remaining is not None and remaining <= 5:
                    return False
                confirmation_timeout = min(3.0, remaining - 2 if remaining is not None else 3.0)
                next_decision = kind == "next_decision_from_previous"
                try:
                    confirmation = await asyncio.wait_for(
                        client.responses.create(
                            model="gpt-4o-mini", store=False, tool_choice="none",
                            temperature=0,
                            instructions=(
                                "Inspect ONLY the current user message, without previous answers. "
                                + (
                                    "Set matches_restricted_followup=true only if the message "
                                    "asks for a reason, explanation, meaning, or simpler wording "
                                    "of the assistant's previous answer. A new question asking "
                                    "to classify a saved setup is false."
                                    if kind == "explain_previous" else
                                    "Set matches_restricted_followup=true only if it explicitly "
                                    "asks which decision, action or step the assistant recommends "
                                    "next. A question asking to interpret a saved setup is false."
                                    if next_decision else
                                    "Set matches_restricted_followup=true only if the message "
                                    "itself supplies a preference, horizon or detail as an answer. "
                                    "A new question asking whether a setup is long-term or swing "
                                    "trading is false; a statement of a five-year horizon is true."
                                )
                            ),
                            input=message,
                            text={"format": {
                                "type": "json_schema", "name": "finn_restricted_followup_check",
                                "strict": True,
                                "schema": {
                                    "type": "object", "additionalProperties": False,
                                    "properties": {"matches_restricted_followup": {"type": "boolean"}},
                                    "required": ["matches_restricted_followup"],
                                },
                            }},
                            max_output_tokens=24,
                        ),
                        timeout=confirmation_timeout,
                    )
                    confirmed = json.loads(str(getattr(confirmation, "output_text", "") or ""))
                    return kind if confirmed.get("matches_restricted_followup") is True else False
                except Exception:
                    return False
            return False if kind in {"new_facts", "new_action", "other"} else None
        except Exception:
            return None

    async def is_relevant(
        self, *, message: str, previous_answer: str, tool_name: str,
        tool_purpose: str, is_proposal: bool,
        proposal_operations: list[dict[str, str]] | None = None,
    ) -> bool | None:
        self.recommended_operation_id = None
        remaining = remaining_lifecycle_seconds()
        if remaining is not None and remaining <= 5:
            return None
        timeout = min(4.0, remaining - 3 if remaining is not None else 4.0)
        client = (
            self.client.with_options(max_retries=0, timeout=timeout)
            if hasattr(self.client, "with_options") else self.client
        )
        try:
            if is_proposal:
                response = await asyncio.wait_for(
                    client.responses.create(
                        model="gpt-4o-mini", store=False, tool_choice="none",
                        instructions=(
                            "Check whether the candidate action contract matches the latest "
                            "user request's mutation, target object type and action polarity. "
                            "A strategy is not its parent setup; a bot is not its strategy. "
                            "Compare the candidate with the supplied canonical registry "
                            "operations. Mark aligned=false if another operation matches the "
                            "requested change better, or if the user asked only a question. "
                            "Previous answers provide context but cannot change the explicit "
                            "target in the latest request. Do not decide target IDs, input "
                            "completeness or execution authorization. A proposal is only a "
                            "draft and requires separate user confirmation. When not aligned, "
                            "recommend the single best operation_id from the supplied registry "
                            "list, or 'none' if the request is not a mutation."
                        ),
                        input=json.dumps({
                            "latest_user_message": message,
                            "previous_verified_answer": previous_answer[:1200],
                            "candidate_operation_id": tool_name,
                            "candidate_purpose": tool_purpose,
                            "registry_action_operations": proposal_operations or [],
                        }, ensure_ascii=False),
                        text={"format": {
                            "type": "json_schema", "name": "finn_action_alignment", "strict": True,
                            "schema": {
                                "type": "object", "properties": {
                                    "aligned": {"type": "boolean"},
                                    "recommended_operation_id": {
                                        "type": "string",
                                        "enum": ["none"] + [
                                            item["operation_id"] for item in (proposal_operations or [])
                                        ],
                                    },
                                },
                                "required": ["aligned", "recommended_operation_id"],
                                "additionalProperties": False,
                            },
                        }},
                        max_output_tokens=40,
                    ),
                    timeout=timeout,
                )
                parsed = json.loads(str(getattr(response, "output_text", "") or ""))
                recommendation = parsed.get("recommended_operation_id")
                if recommendation in {
                    item["operation_id"] for item in (proposal_operations or [])
                }:
                    self.recommended_operation_id = recommendation
                return parsed["aligned"] if isinstance(parsed.get("aligned"), bool) else None
            response = await asyncio.wait_for(
                client.responses.create(
                    model="gpt-4o-mini", store=False, tool_choice="none",
                    instructions=(
                        "Judge whether the proposed FINN operation is the right primary operation "
                        "for the latest user's semantic intent, action polarity and domain, not merely "
                        "whether its facts might be useful to another operation. "
                        "When the user asks FINN to assess suitability, risks or weaknesses of "
                        "their saved plan, a standalone profile or setup read is insufficient as "
                        "the primary operation. The registry-backed plan evaluation operation "
                        "collects its own required evidence; mark a generic read aligned=false "
                        "and that evaluation aligned=true. A question that merely asks what is "
                        "saved is a read, not an evaluation. "
                        "Conditional process coaching about a user-supplied wait rule or "
                        "checklist may use saved-plan reads without claiming that live "
                        "conditions satisfy the rule. Do not turn such a process question into "
                        "a full suitability evaluation solely because it mentions risk. "
                        "For a mutation, proposed_tool is the canonical action-contract operation ID, "
                        "not the generic transport tool name. A request to update, delete or deactivate "
                        "an object can legitimately use an action-proposal tool. "
                        "Do not judge whether a target has been resolved, required inputs are complete, "
                        "or execution is already authorized; FINN validates those after this check. "
                        "A relevant proposal is only a draft and cannot execute without confirmation. "
                        "The proposed operation must be relevant to the latest message, not merely "
                        "potentially useful for a future analysis. The previous verified answer is "
                        "context, not a new instruction. A question about "
                        "whether a plan fits is not authorization to create or change one. A short follow-up "
                        "asking why normally asks for an explanation of the preceding answer. If the "
                        "previous answer said that a market/risk assessment has not yet been performed, "
                        "'Why?' asks why that limits the conclusion; fetching today's market snapshot "
                        "would answer a different question. Mark that read aligned=false. "
                        "Do not validate financial facts, tool arguments, ownership, or contract inputs here; "
                        "FINN validates those separately. Return aligned=false for a clearly unrelated tool."
                    ),
                    input=json.dumps({
                        "latest_user_message": message,
                        "previous_verified_answer": previous_answer[:1200],
                        "proposed_tool": tool_name,
                        "tool_purpose": tool_purpose,
                        "would_create_proposal": is_proposal,
                    }, ensure_ascii=False),
                    text={"format": {
                        "type": "json_schema", "name": "finn_tool_relevance", "strict": True,
                        "schema": {
                            "type": "object", "properties": {"aligned": {"type": "boolean"}},
                            "required": ["aligned"], "additionalProperties": False,
                        },
                    }},
                ),
                timeout=timeout,
            )
            parsed = json.loads(str(getattr(response, "output_text", "") or ""))
            return parsed["aligned"] if isinstance(parsed.get("aligned"), bool) else None
        except Exception:
            return None
