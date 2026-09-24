"""Model-driven FINN entrypoint before the existing action safety pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
import logging
import os
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
    ) -> FinnResponsesFrontDoorResult:
        selected: RequestAnalysisResult | None = None
        read_context: list[dict[str, Any]] = []
        pending_operation = FinnV2OperationStateService.pending_operation_id(conversation_context)
        guided_state = dict(conversation_context.get("active_guided_operation") or {})
        requested_slot = str(guided_state.get("next_missing_input") or "")
        if pending_operation and requested_slot and not FinnV2OperationStateService.is_cancel_intent(message):
            contract = self.proposals.registry.require_supported(pending_operation)
            normalized_message = message.strip().casefold()
            switches_operation = any(
                normalized_message.startswith(alias.casefold())
                for other in self.proposals.registry.list()
                if other.operation_id != pending_operation
                for alias in other.aliases
            )
            states = self.proposals.states
            binds_slot = states._requested_slot_value(
                field=requested_slot, text=message, contract=contract,
            ) is not None or states._is_explicit_correction(message)
            if binds_slot and not switches_operation and "?" not in message:
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
                    selected, previous_response,
                )
        target_retry_used = False
        relevance_retry_used = False
        guard = getattr(self, "relevance_guard", None)
        previous_answer_only = False
        if (
            guard is not None and previous_response and previous_response.get("answer") and not pending_operation
            and not resuming_clarification and len(message.strip().split()) <= 4
        ):
            sufficiency = await guard.previous_answer_suffices(
                message=message,
                previous_answer=str(previous_response.get("answer") or ""),
            )
            previous_answer_only = sufficiency is not False
        tool_purposes = {
            item["name"]: item.get("description", "")
            for item in FinnResponsesToolCatalog().definitions()
        }

        async def execute(call: FinnResponsesToolCall) -> dict[str, Any]:
            nonlocal selected, target_retry_used, relevance_retry_used
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
            should_check = (
                not pending_operation
                and not resuming_clarification
                and (
                    call.operation_id is not None
                    or (
                        call.name.startswith("get_")
                        and previous_response
                        and len(message.strip().split()) <= 4
                    )
                )
                and not conversation_context.get("proposal_revision")
            )
            if should_check and guard is not None:
                contract = (
                    self.proposals.registry.require_supported(call.operation_id)
                    if call.operation_id else None
                )
                purpose = (
                    f"{contract.action_polarity.value} {contract.domain}"
                    if contract and contract.action_polarity
                    else tool_purposes.get(call.name, call.name)
                )
                aligned = await guard.is_relevant(
                    message=message,
                    previous_answer=str((previous_response or {}).get("answer") or ""),
                    tool_name=call.operation_id or call.name,
                    tool_purpose=str(purpose or call.name),
                    is_proposal=call.operation_id is not None,
                )
                if aligned is None and call.operation_id is None:
                    return {"status": "unavailable", "reason": "tool_relevance_unverified"}
                if aligned is None:
                    logger.info("FINN proposal relevance undecided; continuing to contract validation: %s", call.operation_id)
                if not aligned:
                    if relevance_retry_used:
                        return {"status": "unavailable", "reason": "tool_not_relevant_to_request"}
                    relevance_retry_used = True
                    return {
                        "status": "retry", "reason": "tool_not_relevant_to_request",
                        "instruction": (
                            "The candidate tool does not match the latest user request. "
                            "Reconsider the request and previous verified answer, then choose "
                            "a relevant read, answer_directly, or a proposal only if a mutation was requested. "
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
                read_result = await self.reads(call)
                read_context.append(read_result)
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
            missing = set(state.get("missing_required_inputs") or [])
            if (
                not pending_operation
                and not target_retry_used
                and call.operation_id.startswith(("update_", "delete_", "deactivate_"))
                and missing.intersection({"setup_id", "strategy_id", "bot_id"})
            ):
                session_factory = getattr(self.reads, "session_factory", None)
                if session_factory is not None:
                    async with session_factory() as session:
                        resolver = FinnV2EntityResolutionService(session)
                        alternatives = [
                            await resolver.resolve_canonical_target(
                                user_id=self.user_id, entity_type=entity_type,
                                message=message, conversation_context=dict(conversation_context),
                            )
                            for entity_type in ("setup", "strategy", "bot")
                            if entity_type != self.proposals.registry.require_supported(call.operation_id).domain
                        ]
                    explicit_matches = [
                        target for target in alternatives
                        if target.resolution_status == "resolved" and target.source == "explicit_name"
                    ]
                    if len(explicit_matches) == 1:
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

        result = await FinnResponsesLoop(
            client=self.client, executor=execute, on_tool_result=checkpoint,
            model=os.getenv("FINN_RESPONSES_CHAT_MODEL", "gpt-4o-mini"),
        ).run(
            message=model_message or message,
            instructions=instructions,
            previous_response_id=(
                previous_response_id
                if previous_response_id and not previous_response_id.startswith("guided-")
                else None
            ),
            previous_verified_answer=(
                str(previous_response.get("answer") or "")[:1600]
                if previous_response and not resuming_clarification else None
            ),
            guided_operation_id=pending_operation,
            resuming_clarification=resuming_clarification,
            previous_answer_only=previous_answer_only,
        )
        if pending_operation and selected is None:
            raise FinnResponsesError("guided_proposal_tool_call_required")
        recent_action_result = dict(conversation_context.get("previous_action_result") or {})
        if recent_action_result.get("owner_user_id") != self.user_id or recent_action_result.get("result_status") != "succeeded":
            recent_action_result = {}
        return FinnResponsesFrontDoorResult(result, selected, previous_response, recent_action_result or None)
