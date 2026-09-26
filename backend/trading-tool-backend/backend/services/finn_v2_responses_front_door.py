"""Model-driven FINN entrypoint before the existing action safety pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import logging
import os
from time import monotonic
from typing import Any, Mapping

from backend.services.asset_catalog_service import mentioned_catalog_symbols, resolve_catalog_symbol
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_responses_loop import FinnResponsesError, FinnResponsesLoop, FinnResponsesResult
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCatalog
from backend.services.finn_v2_responses_tool_relevance import FinnResponsesToolRelevanceGuard
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinnResponsesFrontDoorResult:
    response: FinnResponsesResult
    proposal_analysis: RequestAnalysisResult | None
    previous_response: dict[str, Any] | None = None
    recent_action_result: dict[str, Any] | None = None
    locale: str = "nl"


class FinnResponsesFrontDoor:
    def __init__(self, *, client: Any, session: Any = None, session_factory: Any = None, user_id: int, run_id: str) -> None:
        self.client = client
        self.user_id = user_id
        self.run_id = run_id
        self.reads = FinnResponsesReadExecutor(
            session=session, session_factory=session_factory, user_id=user_id, run_id=run_id,
        )
        self.proposals = FinnResponsesProposalSelection()
        self.relevance_guard = FinnResponsesToolRelevanceGuard(client)

    @staticmethod
    def binds_guided_slot(*, message: str, contract: Any, registry: Any, requested_slot: str) -> bool:
        """A short typed answer belongs to the persisted slot, not a new model intent."""
        states = FinnV2OperationStateService()
        normalized = message.strip().casefold()
        if not normalized or "?" in message or states.is_cancel_intent(message):
            return False
        if any(
            normalized.startswith(alias.casefold())
            for other in registry.list()
            if other.operation_id != contract.operation_id
            for alias in other.aliases
        ):
            return False
        return (
            states._requested_slot_value(field=requested_slot, text=message, contract=contract) is not None
            and states._is_short_slot_answer(message, requested_slot=requested_slot)
        )

    async def run(
        self,
        *,
        message: str,
        instructions: str,
        conversation_context: Mapping[str, object],
        verified_asset: str | None,
        previous_response_id: str | None = None,
        previous_response: dict[str, Any] | None = None,
        prior_tool_trace: tuple[dict[str, Any], ...] = (),
        model_message: str | None = None,
        resuming_clarification: bool = False,
        locale: str = "nl",
    ) -> FinnResponsesFrontDoorResult:
        selected: RequestAnalysisResult | None = None
        read_context: list[dict[str, Any]] = []
        completed_read_calls: set[tuple[str, str]] = set()
        attempted_evaluation: str | None = None
        pending_operation = FinnV2OperationStateService.pending_operation_id(conversation_context)
        guided_state = dict(conversation_context.get("active_guided_operation") or {})
        requested_slot = str(guided_state.get("next_missing_input") or "")
        if pending_operation and requested_slot and not FinnV2OperationStateService.is_cancel_intent(message):
            contract = self.proposals.registry.require_supported(pending_operation)
            states = self.proposals.states
            switches_operation = any(
                message.strip().casefold().startswith(alias.casefold())
                for other in self.proposals.registry.list()
                if other.operation_id != pending_operation
                for alias in other.aliases
            )
            if self.binds_guided_slot(
                message=message, contract=contract, registry=self.proposals.registry,
                requested_slot=requested_slot,
            ) or (states._is_explicit_correction(message) and not switches_operation and "?" not in message):
                selected = self.proposals.from_call(
                    call=FinnResponsesToolCall(
                        name=FinnResponsesToolCatalog().proposal_tool_for_operation(pending_operation),
                        operation_id=pending_operation, inputs={}, read_tools=(),
                        required_inputs=contract.required_inputs,
                        missing_inputs=tuple(guided_state.get("missing_required_inputs") or ()),
                        draft_intent="new",
                    ),
                    message=message, conversation_context=conversation_context,
                    verified_asset=verified_asset,
                )
                return FinnResponsesFrontDoorResult(
                    FinnResponsesResult(
                        text="Het concept is bijgewerkt.",
                        response_id=previous_response_id or f"guided-{self.run_id}",
                        tool_trace=({
                            "name": "guided_slot_binding", "status": "completed",
                            "result": {"operation_id": pending_operation, "requested_slot": requested_slot},
                        },),
                    ),
                    selected, previous_response, locale=locale,
                )
        target_retry_used = False
        relevance_retry_used = False
        recommended_read_operation: str | None = None
        guard = getattr(self, "relevance_guard", None)
        previous_answer_only = False
        next_decision_from_previous = False
        answering_previous_question = False
        resolved_detail_clarification = False
        pending_clarification = dict(conversation_context.get("responses_clarification") or {})
        detail_clarification = (
            resuming_clarification
            and pending_clarification.get("reason") == "user_detail_required"
        )
        if (
            guard is not None and previous_response and previous_response.get("answer") and not pending_operation
            and (not resuming_clarification or detail_clarification)
            and len(message.strip().split()) <= 12
        ):
            classification_started = monotonic()
            sufficiency = await guard.previous_answer_suffices(
                message=message,
                previous_answer=str(previous_response.get("answer") or ""),
            )
            previous_answer_only = sufficiency in {
                "explain_previous", "next_decision_from_previous",
                "answers_previous_question",
            }
            next_decision_from_previous = sufficiency == "next_decision_from_previous"
            answering_previous_question = sufficiency == "answers_previous_question"
            if detail_clarification and not answering_previous_question:
                previous_answer_only = False
                next_decision_from_previous = False
            logger.info(
                "FINN Responses follow-up classification completed in %.2fs, kind=%s",
                monotonic() - classification_started,
                sufficiency if isinstance(sufficiency, str) else "other",
            )
            if detail_clarification and answering_previous_question:
                resolved_detail_clarification = True
                resuming_clarification = False
                model_message = message
        tool_purposes = {
            item["name"]: item.get("description", "")
            for item in FinnResponsesToolCatalog().definitions()
        }

        async def execute(call: FinnResponsesToolCall) -> dict[str, Any]:
            nonlocal selected, target_retry_used, relevance_retry_used, recommended_read_operation, attempted_evaluation
            if call.name == "ask_for_clarification":
                prior_read_completed = any(
                    item.get("status") == "completed"
                    and str(item.get("name") or "").startswith("get_")
                    for item in prior_tool_trace
                )
                if not read_context and not prior_read_completed and not previous_response:
                    return {"status": "unavailable", "reason": "read_required_before_clarification"}
                return {
                    "status": "needs_input",
                    "reason": call.inputs["reason"],
                    "question": call.inputs["question"],
                }
            if attempted_evaluation and (call.name.startswith("get_") or call.evaluation_operation_id):
                return {
                    "status": "retry", "reason": "evaluation_already_attempted_this_turn",
                    "finalize_now": True,
                    "instruction": (
                        "The registry evaluation has already run in this turn. Do not repeat it "
                        "or fetch a subset of the same required scopes. Answer using its typed "
                        "result, including any unavailable evidence, without claiming a new assessment."
                    ),
                }
            should_check = (
                not pending_operation
                and not resuming_clarification
                and (
                    call.operation_id is not None
                    or call.evaluation_operation_id is not None
                    or call.name.startswith("get_")
                )
                and not conversation_context.get("proposal_revision")
            )
            if should_check and guard is not None:
                contract = (
                    self.proposals.registry.require_supported(call.operation_id or call.evaluation_operation_id)
                    if call.operation_id or call.evaluation_operation_id else None
                )
                purpose = (
                    str(contract.semantic_description or contract.operation_id)
                    if contract and call.evaluation_operation_id
                    else f"{contract.action_polarity.value} {contract.domain}"
                    if contract and contract.action_polarity
                    else tool_purposes.get(call.name, call.name)
                )
                preferred = None
                choose_read = getattr(guard, "preferred_read_operation", None)
                if (call.name.startswith("get_") or call.evaluation_operation_id) and not read_context and callable(choose_read) and recommended_read_operation is None:
                    relevance_started = monotonic()
                    options = [
                        {"operation_id": item.operation_id,
                         "purpose": str(item.semantic_description or item.operation_id)}
                        for item in self.proposals.registry.list()
                        if item.supported and item.mode == "EVALUATE"
                        and item.model_policy == "required" and item.required_scopes
                    ]
                    preferred = await choose_read(
                        message=message,
                        previous_answer=str((previous_response or {}).get("answer") or ""),
                        proposed_tool=call.name,
                        proposed_purpose=str(purpose or call.name),
                        evaluation_options=options,
                        read_options=[
                            {"operation_id": name, "purpose": description}
                            for name, description in tool_purposes.items()
                            if name.startswith("get_")
                        ],
                    )
                    logger.info(
                        "FINN Responses primary-read relevance completed in %.2fs changed=%s",
                        monotonic() - relevance_started, bool(preferred and preferred != call.name),
                    )
                    if preferred and preferred != call.name:
                        if relevance_retry_used:
                            return {"status": "unavailable", "reason": "tool_not_relevant_to_request"}
                        relevance_retry_used = True
                        recommended_read_operation = preferred
                        return {
                            "status": "retry", "reason": "primary_operation_mismatch",
                            "recommended_tool_name": preferred,
                            "instruction": (
                                "The primary operation selected from FINN's existing registry is "
                                f"{preferred}. The proposed tool was not executed. Call that "
                                "operation with its declared arguments; its contract gathers required evidence."
                            ),
                        }
                relevance_started = monotonic()
                aligned = (
                    preferred == call.name
                    or (recommended_read_operation is not None
                        and (call.evaluation_operation_id or call.name) == recommended_read_operation)
                    or await guard.is_relevant(
                    message=message,
                    previous_answer=str((previous_response or {}).get("answer") or ""),
                    tool_name=call.operation_id or call.evaluation_operation_id or call.name,
                    tool_purpose=str(purpose or call.name),
                    is_proposal=call.operation_id is not None,
                    **({"proposal_operations": [
                        {
                            "operation_id": item.operation_id,
                            "domain": item.domain,
                            "polarity": item.action_polarity.value if item.action_polarity else "",
                            "purpose": str(item.semantic_description or item.operation_id),
                        }
                        for item in self.proposals.registry.list()
                        if item.supported and item.mode in {"CREATE_PROPOSAL", "ACTION_PROPOSAL"}
                    ]} if call.operation_id else {}),
                    )
                )
                logger.info(
                    "FINN Responses tool relevance completed in %.2fs verified=%s",
                    monotonic() - relevance_started, aligned is not None,
                )
                if aligned is None:
                    return {"status": "unavailable", "reason": "tool_relevance_unverified"}
                if not aligned:
                    if relevance_retry_used:
                        return {"status": "unavailable", "reason": "tool_not_relevant_to_request"}
                    relevance_retry_used = True
                    recommended_operation_id = (
                        getattr(guard, "recommended_operation_id", None)
                        if call.operation_id else None
                    )
                    recommended_tool_name = (
                        FinnResponsesToolCatalog().proposal_tool_for_operation(recommended_operation_id)
                        if recommended_operation_id else None
                    )
                    return {
                        "status": "retry", "reason": "tool_not_relevant_to_request",
                        **({"recommended_operation_id": recommended_operation_id,
                            "recommended_tool_name": recommended_tool_name}
                           if recommended_tool_name else {}),
                        "instruction": (
                            "The candidate tool is not the right primary operation for the latest "
                            "request. Reconsider the user's intended outcome and the registry-backed "
                            "evaluation contracts as well as reads; choose the operation that can "
                            "actually answer it. Use a proposal only if a mutation was requested. "
                            "No tool was executed and no proposal was created."
                        ),
                    }
            if call.operation_id is None:
                previous_setup_target: dict[str, object] = {}
                if call.name == "get_active_plan_and_strategy":
                    # The model can express the choice, but only the user's text
                    # and owner-scoped persisted evidence may select the object.
                    reference = call.inputs.get("reference")
                    prior_setups = [
                        item for prior_call in (previous_response or {}).get("tool_trace", [])
                        for item in (prior_call.get("result", {}).get("results") or [])
                        if item.get("scope") == "read_active_setup"
                        and item.get("status") == "completed"
                        and isinstance(item.get("data"), dict)
                        and item["data"].get("setup_id")
                    ]
                    prior_name = str(prior_setups[-1]["data"].get("name") or "") if prior_setups else ""
                    matches_prior_name = bool(
                        prior_name and call.inputs.get("setup_name", "").casefold() == prior_name.casefold()
                    )
                    if reference == "previous_response" or matches_prior_name:
                        if prior_setups:
                            previous_setup_target = {
                                "entity_type": "setup",
                                "entity_id": prior_setups[-1]["data"]["setup_id"],
                            }
                        elif reference == "previous_response":
                            action_result = dict(conversation_context.get("previous_action_result") or {})
                            if (
                                action_result.get("owner_user_id") == self.user_id
                                and action_result.get("result_status") == "succeeded"
                                and action_result.get("entity_type") == "setup"
                                and action_result.get("entity_id") is not None
                            ):
                                previous_setup_target = {
                                    "entity_type": "setup",
                                    "entity_id": action_result["entity_id"],
                                }
                        if reference == "previous_response" and not previous_setup_target and not resuming_clarification:
                            return {"status": "unavailable", "reason": "previous_response_reference_unavailable"}
                    call = replace(call, inputs={
                        key: value for key, value in call.inputs.items()
                        if key not in {"setup_name", "reference"}
                    })
                model_asset = call.inputs.get("asset")
                if model_asset:
                    symbol = resolve_catalog_symbol(model_asset)
                    if symbol not in mentioned_catalog_symbols(message):
                        call = replace(call, inputs={key: value for key, value in call.inputs.items() if key != "asset"})
                    else:
                        call = replace(call, inputs={**call.inputs, "asset": symbol})
                if (
                    call.name == "get_active_plan_and_strategy"
                    and not FinnV2EntityResolutionService.is_setup_collection_request(message)
                ):
                    session_factory = getattr(self.reads, "session_factory", None)
                    if session_factory is not None:
                        async with session_factory() as session:
                            target = await FinnV2EntityResolutionService(session).resolve_canonical_target(
                                user_id=self.user_id, entity_type="setup", message=message,
                                conversation_context=(
                                    {"canonical_entity_target": previous_setup_target}
                                    if previous_setup_target else (
                                        dict(conversation_context)
                                        if FinnV2EntityResolutionService.references_recent_action(message, "setup")
                                        else {}
                                    )
                                ),
                                selector={
                                    **call.inputs,
                                    "asset_source": (
                                        "explicit_message" if call.inputs.get("asset")
                                        and call.inputs["asset"] in mentioned_catalog_symbols(message)
                                        else "context"
                                    ),
                                },
                            )
                        if target.resolution_status == "resolved":
                            call = replace(call, inputs={"setup_id": target.entity_id})
                if call.evaluation_operation_id and resuming_clarification:
                    chosen_setups = [
                        item for prior_read in read_context
                        for item in (prior_read.get("results") or [])
                        if item.get("scope") == "read_active_setup"
                        and item.get("status") == "completed"
                        and isinstance(item.get("data"), dict)
                        and item["data"].get("setup_id") is not None
                    ]
                    if len({item["data"]["setup_id"] for item in chosen_setups}) == 1:
                        call = replace(call, inputs={
                            **call.inputs, "setup_id": chosen_setups[-1]["data"]["setup_id"],
                        })
                read_identity = (call.name, repr(sorted(call.inputs.items())))
                if call.read_tools and read_identity in completed_read_calls:
                    return {
                        "status": "retry", "reason": "read_already_completed_this_turn",
                        "instruction": (
                            "That same FINN read already returned evidence in this turn. Do not repeat it. "
                            "Use the existing typed result to answer the latest question, or ask one "
                            "specific clarification if a user choice is genuinely missing."
                        ),
                    }
                read_result = await self.reads(call)
                read_context.append(read_result)
                completed_read_calls.add(read_identity)
                if call.evaluation_operation_id:
                    attempted_evaluation = call.evaluation_operation_id
                return read_result
            if pending_operation and call.operation_id != pending_operation:
                return {"status": "unavailable", "reason": "guided_operation_still_active"}
            if selected is not None:
                return {"status": "unavailable", "reason": "one_proposal_per_run"}
            analysis = self.proposals.from_call(
                call=call,
                message=message,
                conversation_context=conversation_context,
                verified_asset=verified_asset,
                read_context=read_context,
            )
            state = analysis.request_plan.operation_state
            if (
                not pending_operation
                and call.operation_id.startswith(("update_", "delete_", "deactivate_"))
                and self.proposals.registry.require_supported(call.operation_id).domain
                in {"setup", "strategy", "bot"}
            ):
                candidate_domain = self.proposals.registry.require_supported(call.operation_id).domain
                check_domain = getattr(guard, "requested_mutation_domain", None)
                if callable(check_domain):
                    registry_domains = [
                        {"domain": domain, "purpose": next(
                            str(item.semantic_description or item.operation_id)
                            for item in self.proposals.registry.list()
                            if item.supported and item.domain == domain
                        )}
                        for domain in ("setup", "strategy", "bot")
                    ]
                    requested_domain = await check_domain(
                        message=message, domains=registry_domains,
                    )
                    if requested_domain in {None, "unknown"}:
                        return {"status": "unavailable", "reason": "write_target_domain_unverified"}
                    if requested_domain != candidate_domain:
                        if target_retry_used:
                            return {"status": "unavailable", "reason": "write_target_domain_mismatch"}
                        target_retry_used = True
                        return {
                            "status": "retry",
                            "reason": "requested_object_type_mismatch",
                            "candidate_operation_id": call.operation_id,
                            "target_domain": requested_domain,
                            "instruction": (
                                "The user's requested object kind differs from the candidate. "
                                "Choose only a registry operation for the requested kind; "
                                "if no owner-scoped object exists, ask for clarification."
                            ),
                        }
                session_factory = getattr(self.reads, "session_factory", None)
                if session_factory is not None:
                    async with session_factory() as session:
                        resolver = FinnV2EntityResolutionService(session)
                        targets = [
                            await resolver.resolve_canonical_target(
                                user_id=self.user_id, entity_type=entity_type,
                                message=message, conversation_context=dict(conversation_context),
                            )
                            for entity_type in ("setup", "strategy", "bot")
                        ]
                    candidate_name_length = max((
                        len(target.display_name or "") for target in targets
                        if target.entity_type == candidate_domain
                        and target.resolution_status == "resolved"
                        and target.source == "explicit_name"
                    ), default=0)
                    explicit_matches = [
                        target for target in targets
                        if target.entity_type != candidate_domain
                        and target.resolution_status == "resolved"
                        and target.source == "explicit_name"
                        and len(target.display_name or "") > candidate_name_length
                    ]
                    if len(explicit_matches) == 1:
                        if target_retry_used:
                            return {"status": "unavailable", "reason": "write_target_domain_mismatch"}
                        target_retry_used = True
                        return {
                            "status": "retry",
                            "reason": "owner_scoped_target_type_mismatch",
                            "candidate_operation_id": call.operation_id,
                            "target_domain": explicit_matches[0].entity_type,
                            "instruction": (
                                "The saved object named in the request belongs to the indicated domain, "
                                "not the candidate action's domain. Reconsider the requested operation. "
                                "FINN keeps the owner-scoped object ID server-side."
                            ),
                        }
            selected = analysis
            return {
                "status": "needs_input" if state.get("missing_required_inputs") else "validation_pending",
                "operation_id": call.operation_id,
                "supplied_inputs": {
                    key: value for key, value in dict(state.get("collected_inputs") or {}).items()
                    if not key.endswith("_id")
                },
                "missing_inputs": state.get("missing_required_inputs", []),
                "confirmation_required": True,
            }

        async def checkpoint(response_id: str, trace: tuple[dict[str, Any], ...]) -> None:
            session_factory = getattr(self.reads, "session_factory", None)
            if session_factory is None:
                return
            async with session_factory() as session:
                await FinnV2RuntimeContractRepository(session).record_responses_progress(
                    run_id=self.run_id, user_id=self.user_id,
                    response_id=response_id, tool_trace=list(trace),
                )
                await session.commit()

        loop_started = monotonic()
        result = await FinnResponsesLoop(
            client=self.client, executor=execute, on_tool_result=checkpoint,
            model=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-4o-mini"),
        ).run(
            message=model_message or message,
            instructions=instructions,
            previous_response_id=(
                previous_response_id
                if previous_response_id and not resuming_clarification
                and not previous_response_id.startswith("guided-")
                else None
            ),
            previous_verified_answer=(
                str(previous_response.get("answer") or "")[:1600]
                if previous_response and not resuming_clarification else None
            ),
            antecedent_verified_answer=(
                str(previous_response.get("antecedent_verified_answer") or "")[:1600]
                if previous_response and not resuming_clarification else None
            ),
            guided_operation_id=pending_operation,
            resuming_clarification=resuming_clarification,
            resume_evaluation_operation_id=(
                next((
                    str((item.get("result") or {})["evaluation_operation_id"])
                    for item in reversed((previous_response or {}).get("tool_trace") or [])
                    if (item.get("result") or {}).get("evaluation_operation_id")
                ), None)
                if resuming_clarification else None
            ),
            original_user_request=(
                str(conversation_context.get("responses_clarification", {}).get("original_message") or "")
                if resuming_clarification or resolved_detail_clarification else ""
            ),
            previous_answer_only=previous_answer_only,
            next_decision_from_previous=next_decision_from_previous,
            answering_previous_question=answering_previous_question,
            conditional_process_check=lambda: bool(
                getattr(guard, "conditional_process", False)
                and getattr(guard, "response_focus", None) != "priorities"
            ),
            response_focus_check=lambda: getattr(guard, "response_focus", None),
            locale=locale,
        )
        logger.info("FINN Responses tool loop completed in %.2fs", monotonic() - loop_started)
        if pending_operation and selected is None:
            raise FinnResponsesError("guided_proposal_tool_call_required")
        recent_action_result = dict(conversation_context.get("previous_action_result") or {})
        if recent_action_result.get("owner_user_id") != self.user_id or recent_action_result.get("result_status") != "succeeded":
            recent_action_result = {}
        return FinnResponsesFrontDoorResult(result, selected, previous_response, recent_action_result or None, locale)
