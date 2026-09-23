from __future__ import annotations

import logging
from contextlib import suppress
from datetime import datetime, timedelta, timezone
import asyncio
from dataclasses import replace
from time import monotonic
from types import SimpleNamespace
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import (
    FinnV2ModeContractError,
    TRACE_EVENT_BY_STATUS,
    build_placeholder_response,
    is_terminal_status,
    normalize_interaction_mode,
    validate_run_transition,
)
from backend.domain.finn_v2_runtime_contract import build_terminal_runtime_contract
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.infrastructure.repositories.finn_v2_trace_repository import FinnV2TraceRepository
from backend.infrastructure.database import async_session_factory
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_lifecycle_budget import (
    remaining_lifecycle_seconds,
    reset_lifecycle_deadline,
    set_lifecycle_deadline,
)
from backend.schemas.finn_v2_schema import AgentRunStatusEnvelope, PolicyDecision, VerifiedResponse
from backend.schemas.finn_v2_orchestrator_schema import LifecyclePhaseOutcome
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesVerifiedAnswer
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor, FinnResponsesFrontDoorResult
from backend.services.finn_v2_responses_loop import FinnResponsesError
from backend.utils import openai_client


logger = logging.getLogger(__name__)


class FinnV2RunService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.conversations = FinnV2ConversationRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.runtime_contracts = FinnV2RuntimeContractRepository(session)
        self.traces = FinnV2TraceRepository(session)
        self.tools = FinnV2ToolExecutionService(session)
        self.delivery = FinnV2DeliveryService(session)
        self.orchestrator = FinnV2OrchestratorService(session, phase_transition=self.persist_transition)

    async def create_run(self, payload: Dict[str, Any], *, commit: bool = True):
        try:
            run = await self.runs.create(**payload)
            contract = await self.runtime_contracts.create_for_run(run=run)
            await self.conversations.set_last_run(
                conversation_id=run.conversation_id,
                user_id=run.user_id,
                run_id=run.id,
            )
            await self.traces.append_event(
                run_id=run.id,
                user_id=run.user_id,
                trace_id=run.trace_id,
                event_type="run_created",
                payload_json={**self._trace_payload(run, status="created", response_source=None), "contract_id": contract.contract_id},
            )
            if commit:
                await self.runs._commit_with_rollback(
                    operation="create_run",
                    entity_type="FinnV2Run",
                    run_id=run.id,
                )
        except Exception:
            raise
        return run

    async def complete_responses_read(
        self, *, run_id: str, user_id: int, response_id: str,
        answer: FinnResponsesVerifiedAnswer,
        previous_response: dict[str, Any] | None = None,
    ) -> None:
        """Publish a verified free-chat read through the same polling/SSE model."""
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        status = answer.status
        if status not in {"completed", "unavailable"}:
            raise ValueError("responses_read_terminal_status_invalid")
        validate_run_transition(run.status, status)
        response_json = {
            "mode": "READ" if status == "completed" else "UNAVAILABLE",
            "content": answer.text,
            "response_source": "v2_runtime",
            "verifier_status": "passed" if status == "completed" else "failed",
            "evidence": [],
            "uncertainty": [answer.reason] if answer.reason else [],
            "proposal_id": None,
            "confirmation_required": False,
            "reasoning_provenance": {
                "reasoning_source": "responses_tool_loop",
                "provider_response_id": response_id,
            },
        }
        if previous_response:
            await self.runtime_contracts.record_previous_response_reference(
                run_id=run_id,
                previous_run_id=str(previous_response["run_id"]),
            )
        contract = await self.runtime_contracts.materialize_terminal(
            run_id=run_id, status=status, mode=response_json["mode"],
            response=response_json, error_code=answer.reason,
        )
        response_json["_runtime_contract_projection"] = contract.terminal_projection_json
        await self.runs.update_status(
            run=run, status=status, interaction_mode=response_json["mode"],
            policy_json=PolicyDecision().dict(), response_json=response_json,
            error_code=answer.reason, retryable=False,
            completed_at=datetime.now(timezone.utc),
        )
        await self.traces.append_event(
            run_id=run.id, user_id=run.user_id, trace_id=run.trace_id,
            event_type=TRACE_EVENT_BY_STATUS[status],
            payload_json=self._trace_payload(run, status=status, response_source="v2_runtime"),
        )
        if status == "completed" and run.conversation_id:
            await self.conversations.set_responses_cursor(
                conversation_id=run.conversation_id, user_id=user_id,
                run_id=run_id, response_id=response_id,
            )
        await self._commit_session_if_possible()

    @classmethod
    async def prepare_responses_turn(
        cls, *, run_id: str, user_id: int,
        selector_started: asyncio.Event, selection_ready: asyncio.Event,
        recovery_response_id: str | None = None,
        prior_tool_trace: tuple[dict[str, Any], ...] = (),
    ) -> tuple[FinnResponsesFrontDoorResult, str]:
        """Select through Responses without holding a DB connection at the provider."""
        async with async_session_factory() as session:
            orchestrator = FinnV2OrchestratorService(session)
            run = await orchestrator.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
            if run is None or run.status != "planned":
                raise LookupError("responses_run_not_planned_or_unowned")
            conversation_id = run.conversation_id
            message = run.message
            context = await orchestrator._load_continuation_context(
                conversation_id=conversation_id, user_id=user_id, run_id=run_id,
                has_prior_run=(run.client_context_json or {}).get("_conversation_has_prior_run"),
            )
            cursor = dict(context.get("responses_cursor") or {})
            previous_response = None
            if cursor.get("run_id") and cursor.get("response_id"):
                prior_contract = await orchestrator.runtime_contracts.get_for_run(
                    run_id=str(cursor["run_id"]),
                )
                if (
                    prior_contract is not None
                    and prior_contract.user_id == user_id
                    and prior_contract.conversation_id == conversation_id
                ):
                    prior_state = dict(prior_contract.state_json or {})
                    exchange = dict(prior_state.get("responses_exchange") or {})
                    if (
                        exchange.get("response_id") == cursor["response_id"]
                        and prior_state.get("terminal_status") == "completed"
                    ):
                        previous_response = {
                            "run_id": prior_contract.run_id,
                            "response_id": cursor["response_id"],
                            "answer": dict(prior_state.get("terminal_response") or {}).get("content"),
                            "tool_trace": list(exchange.get("tool_trace") or []),
                        }
            prior_contract = await orchestrator.runtime_contracts.get_latest_for_conversation(
                conversation_id=conversation_id, user_id=user_id, exclude_run_id=run_id,
            ) if conversation_id else None
            prior_state = dict((prior_contract.state_json or {}) if prior_contract else {})
            if prior_state.get("terminal_status") == "unavailable":
                safe_answer = str(dict(prior_state.get("terminal_response") or {}).get("content") or "").strip()
                if safe_answer:
                    exchange = dict(prior_state.get("responses_exchange") or {})
                    progress = dict(prior_state.get("responses_progress") or {})
                    previous_response = {
                        "run_id": prior_contract.run_id,
                        "response_id": None,
                        "answer": safe_answer,
                        "tool_trace": list(exchange.get("tool_trace") or progress.get("tool_trace") or []),
                    }
            guided = dict(context.get("active_guided_operation") or {})
            guided_inputs = dict(guided.get("collected_inputs") or {})
            verified_asset = (
                str(guided_inputs.get("symbol") or guided_inputs.get("asset") or "") or None
            ) if guided.get("missing_required_inputs") else None
        client = openai_client.async_client
        if client is None:
            raise FinnResponsesError("responses_provider_unconfigured")
        selector_started.set()
        async with async_session_factory() as session:
            await FinnV2RuntimeContractRepository(session).record_phase_timestamp(
                run_id=run_id, phase="selector_started",
            )
            await session.commit()
        result = await FinnResponsesFrontDoor(
            client=client, session_factory=async_session_factory,
            user_id=user_id, run_id=run_id,
        ).run(
            message=message,
            instructions=(
                "You are FINN, a grounded personal trading coach. Understand the user's language and "
                "choose zero or more FINN read tools. Personal judgments about the user's plan, risk, "
                "portfolio or market conditions require relevant read tools; use zero tools only for "
                "general educational conversation. Keep the final answer to a few grounded sentences. "
                "A personalized trading-plan assessment needs both the user's profile/risk style and "
                "the active plan/strategy read; if either is ambiguous or unavailable, ask for the "
                "missing context instead of recommending a strategy. "
                "For a standalone question about current indicators, use the indicator and relevant "
                "market tools; do not fetch the active plan or ask which setup is meant unless the user "
                "asks how those indicators affect a specific plan. "
                "For a requested mutation, the proposal operation's entity type must be the object "
                "the user wants to change; a related parent or child object is not the target. "
                "For every user request to create, "
                "update or remove something, ALWAYS call the matching proposal tool immediately, even "
                "when some inputs are missing. Never ask for mutation inputs before that tool call: the "
                "registry-backed tool result determines the missing fields. Read tools may support that "
                "request but can never replace its proposal tool. Do not first require a parent object "
                "or all required inputs: FINN resolves owner-scoped dependencies and asks for gaps. "
                "A proposal is not an execution. "
                "Continue an active guided operation with the same proposal tool and the user's answer "
                "for its pending contract input. Never claim a change is saved before explicit "
                "user confirmation and backend execution. Never invent prices, evidence, ownership or IDs. "
                "When a tool returns partial, unavailable or stale data, describe only what the typed "
                "result establishes and what is still missing. Do not infer live indicator values, "
                "market causes, portfolio effects or a personal recommendation from generic knowledge. "
                "If an owner-scoped read is ambiguous, ask which named object the user means; do not "
                "guess one, claim that no plan exists, or evaluate the whole plan without a unique target. "
                "An unavailable source does not establish that the outage is temporary or why it happened. "
                "If asked why data is missing, say that the current evidence does not establish the "
                "cause; do not invent a provider failure. Reply in the user's language without raw "
                "contract keys, internal IDs or backend error codes. For a proposal tool call, set "
                "draft_intent to new for a new action or revise only when changing a pending draft."
                + (
                    " Your preceding answer could not be verified against FINN evidence. Reconsider the "
                    "original request: if it asks to change a saved object, call its proposal tool now, "
                    "even when a supporting read was unavailable. If it only asks a question, use "
                    "read tools or give an honest limitation; do not propose a mutation."
                    if recovery_response_id else ""
                )
                + (
                    " A pending draft exists for operation "
                    + str(dict(context.get("proposal_revision") or {}).get("operation_id"))
                    + ". When the user changes that draft, call its proposal tool with "
                    "draft_intent=revise and only the changed inputs; FINN retains and validates prior fields."
                    if context.get("proposal_revision") else ""
                )
                + (
                    " This turn follows a verified answer in the same conversation. For a short why/how "
                    "follow-up, explain only what the previous verified answer and its tool results establish. "
                    "Do not invent possible causes, user history, technical failures or missing data beyond "
                    "those actually returned by FINN tools. If the prior response reports unavailable "
                    "market evidence, explain that no verified conclusion about its effect on the plan "
                    "can be drawn until fresh evidence is available."
                    if previous_response else ""
                )
            ),
            conversation_context=context,
            verified_asset=verified_asset,
            previous_response_id=(
                recovery_response_id or (
                    str(previous_response.get("response_id"))
                    if previous_response and previous_response.get("response_id") else None
                )
            ),
            previous_response=previous_response,
        )
        if prior_tool_trace:
            result = replace(
                result,
                response=replace(
                    result.response,
                    tool_trace=prior_tool_trace + result.response.tool_trace,
                ),
            )
        async with async_session_factory() as session:
            contracts = FinnV2RuntimeContractRepository(session)
            await contracts.record_responses_exchange(
                run_id=run_id, user_id=user_id,
                response_id=result.response.response_id,
                tool_trace=list(result.response.tool_trace),
                answer=result.response.text,
            )
            await contracts.record_phase_timestamp(run_id=run_id, phase="selector_completed")
            await session.commit()
        selection_ready.set()
        if result.proposal_analysis is None and any(
            str(call.get("name") or "").endswith("_proposal")
            for call in result.response.tool_trace
        ):
            raise FinnResponsesError("proposal_tool_validation_failed")
        return result, message

    async def transition_run(
        self,
        run_id: str,
        user_id: int,
        *,
        next_status: str,
        interaction_mode: Optional[str] = None,
        policy_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
        response_source: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: bool = False,
    ):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")

        validate_run_transition(run.status, next_status)
        now = datetime.now(timezone.utc)
        completed_at = now if is_terminal_status(next_status) and next_status != "canceled" else None
        canceled_at = now if next_status == "canceled" else None
        async with self.session.begin_nested():
            await self.runtime_contracts.record_lifecycle_status(
                run_id=run_id, status=next_status, mode=interaction_mode
            )
            await self.runs.update_status(
                run=run,
                status=next_status,
                interaction_mode=interaction_mode,
                policy_json=policy_json,
                response_json=response_json,
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                completed_at=completed_at,
                canceled_at=canceled_at,
            )
            await self.traces.append_event(
                run_id=run.id,
                user_id=run.user_id,
                trace_id=run.trace_id,
                event_type=TRACE_EVENT_BY_STATUS[next_status],
                payload_json=self._trace_payload(run, status=next_status, response_source=response_source),
            )
        return run

    async def persist_transition(
        self,
        run_id: str,
        user_id: int,
        *,
        next_status: str,
        interaction_mode: Optional[str] = None,
        policy_json: Optional[dict] = None,
        response_json: Optional[dict] = None,
        response_source: Optional[str] = None,
        error_code: Optional[str] = None,
        error_message: Optional[str] = None,
        retryable: bool = False,
    ):
        run = await self.transition_run(
            run_id,
            user_id,
            next_status=next_status,
            interaction_mode=interaction_mode,
            policy_json=policy_json,
            response_json=response_json,
            response_source=response_source,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
        )
        await self._commit_session_if_possible()
        return run

    async def complete_run(
        self,
        *,
        run_id: str,
        user_id: int,
        phase_outcome: LifecyclePhaseOutcome,
        responses_response_id: str | None = None,
    ):
        get_runtime_contract = getattr(self.runtime_contracts, "get_for_run", None)
        runtime_contract = (
            await get_runtime_contract(run_id=run_id)
            if callable(get_runtime_contract)
            else None
        )
        contract_state = dict(getattr(runtime_contract, "state_json", {}) or {})
        guided_state = dict(contract_state.get("guided_state") or {})
        guided_operation = str(guided_state.get("operation_id") or "")
        is_guided_clarification = (
            phase_outcome.terminal_status == "clarification_required"
            and guided_operation in {"create_setup", "create_strategy", "create_bot"}
            and bool(guided_state.get("missing_required_inputs"))
        )
        # A guided clarification intentionally has no tools, reasoning or
        # verifier artifacts. Reading all those tables after the fast path can
        # consume the terminal reserve for data that cannot exist.
        if is_guided_clarification:
            artifacts = {
                "delivery_envelope": {},
                "verified_response": {},
                "orchestrator_result": {},
                "policy_result": PolicyDecision().dict(),
                "reasoning_result": {},
                "verifier_result": {},
            }
        # A verified successful response already contains the complete public
        # terminal payload. Do not fan out across every diagnostic artifact
        # table before making that response visible; those reads can contend
        # with dashboard traffic and previously consumed the terminal reserve.
        else:
            envelope = (
                await self.delivery.get_delivery_envelope(user_id=user_id, run_id=run_id)
                if hasattr(self.session, "execute")
                else None
            )
            if (
                envelope is not None
                and envelope.response is not None
                and phase_outcome.terminal_status == "completed"
            ):
                artifacts = {
                    "delivery_envelope": envelope.dict(),
                    "verified_response": envelope.response.dict(),
                    "orchestrator_result": {},
                    "policy_result": PolicyDecision().dict(),
                    "reasoning_result": {},
                    "verifier_result": {},
                }
            else:
                artifacts = await self.delivery.get_delivery_artifacts(
                    user_id=user_id, run_id=run_id
                )
        verified = artifacts.get("verified_response") or {}
        orchestrator = artifacts.get("orchestrator_result") or {}
        verifier = artifacts.get("verifier_result") or {}
        reasoning = artifacts.get("reasoning_result") or {}
        policy = artifacts.get("policy_result") or PolicyDecision().dict()
        setup_draft = dict((getattr(runtime_contract, "state_json", {}) or {}).get("setup_draft") or {})
        guided_draft = setup_draft or {
            "operation_id": guided_operation,
            "draft_status": guided_state.get("status"),
            "supplied_inputs": dict(guided_state.get("collected_inputs") or {}),
            "missing_inputs": list(guided_state.get("missing_required_inputs") or []),
            "requested_slot": guided_state.get("next_missing_input"),
        }
        direct_answer = str(verified.get("direct_answer") or "").strip()
        main_observation = str(verified.get("main_observation") or "").strip()
        content = "\n\n".join([part for part in [direct_answer, main_observation] if part]).strip()
        next_status = phase_outcome.terminal_status
        if next_status not in {"clarification_required", "unavailable", "downgraded", "rejected", "completed", "failed"}:
            raise ValueError("invalid_lifecycle_phase_outcome")
        if not content:
            response_json = self._terminal_placeholder_response(
                interaction_mode=phase_outcome.interaction_mode,
                terminal_status=next_status,
                orchestrator=orchestrator,
                verifier=verifier,
                reasoning=reasoning,
                delivery_envelope=artifacts.get("delivery_envelope") or {},
                setup_draft=guided_draft,
            )
        else:
            response_json = {
                "mode": verified.get("mode") or phase_outcome.interaction_mode or "UNAVAILABLE",
                "content": content,
                "response_source": "v2_runtime",
                "verifier_status": verified.get("verifier_status") or "passed",
                "evidence": [],
                "uncertainty": verified.get("uncertainty_codes") or [],
                "proposal_id": verified.get("proposal_id"),
                "confirmation_required": bool(verified.get("confirmation_required")),
                "next_step": verified.get("next_step"),
                "reasoning_provenance": verified.get("reasoning_provenance") or {},
            }
        terminal_reason = self._terminal_reason(
            terminal_status=next_status,
            orchestrator=orchestrator,
            policy=policy,
            verifier=verifier,
            reasoning=reasoning,
        )
        contract = await self.runtime_contracts.materialize_terminal(
            run_id=run_id,
            status=next_status,
            mode=phase_outcome.interaction_mode or response_json["mode"],
            response=response_json,
            error_code=terminal_reason,
        )
        response_json["_runtime_contract_projection"] = contract.terminal_projection_json
        if not hasattr(self.session, "execute"):
            # Preserve the narrow repository-free seam used by unit fixtures.
            await self.persist_transition(
                run_id,
                user_id,
                next_status=next_status,
                interaction_mode=phase_outcome.interaction_mode or response_json["mode"],
                policy_json=policy,
                response_json=response_json,
                response_source="v2_runtime",
            )
            return
        # ``materialize_terminal`` already holds and revises the authoritative
        # runtime-contract row. Calling ``persist_transition`` here used to
        # enter a second savepoint and lock/revise that same row again. Under
        # production concurrency this could consume the complete terminal
        # reserve after a proposal had already been created. Persist the run
        # and trace in this transaction without a second contract transition.
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        validate_run_transition(run.status, next_status)
        now = datetime.now(timezone.utc)
        await self.runs.update_status(
            run=run,
            status=next_status,
            interaction_mode=phase_outcome.interaction_mode or response_json["mode"],
            policy_json=policy,
            response_json=response_json,
            retryable=False,
            completed_at=now,
        )
        await self.traces.append_event(
            run_id=run.id,
            user_id=run.user_id,
            trace_id=run.trace_id,
            event_type=TRACE_EVENT_BY_STATUS[next_status],
            payload_json=self._trace_payload(
                run, status=next_status, response_source="v2_runtime"
            ),
        )
        if responses_response_id and next_status in {"completed", "clarification_required"} and run.conversation_id:
            await self.conversations.set_responses_cursor(
                conversation_id=run.conversation_id, user_id=user_id,
                run_id=run_id, response_id=responses_response_id,
            )
        await self._commit_session_if_possible()

    @staticmethod
    def _terminal_reason(
        *,
        terminal_status: str,
        orchestrator: Dict[str, Any],
        policy: Dict[str, Any],
        verifier: Dict[str, Any],
        reasoning: Dict[str, Any],
    ) -> Optional[str]:
        """Publish one safe typed cause for a limited terminal response.

        The complete error/evidence detail remains in private artifacts.  The
        terminal contract only needs a stable code that distinguishes an
        expected limitation from an internal lifecycle failure.
        """
        if terminal_status not in {"unavailable", "downgraded", "rejected", "failed"}:
            return None
        for source, key in (
            (policy, "blocking_codes"),
            (verifier, "reason_codes"),
            (orchestrator, "unavailable_codes"),
            (reasoning, "uncertainty_codes"),
        ):
            codes = source.get(key) if isinstance(source, dict) else None
            if isinstance(codes, list):
                for code in codes:
                    if isinstance(code, str) and code:
                        return code
        return f"terminal_{terminal_status}"

    def _terminal_placeholder_response(
        self,
        *,
        interaction_mode: Optional[str],
        terminal_status: str,
        orchestrator: Dict[str, Any],
        verifier: Dict[str, Any],
        reasoning: Dict[str, Any],
        delivery_envelope: Dict[str, Any],
        setup_draft: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        placeholder = build_placeholder_response()
        reasoning_result = reasoning.get("result") or {}
        reason_codes = list(verifier.get("reason_codes") or [])
        content = placeholder.get("content") or "FINN V2 kon geen verified response afronden."
        mode = interaction_mode or "UNAVAILABLE"
        verifier_status = "not_run"
        if dict(setup_draft or {}).get("draft_status") == "cancelled":
            content = "Het strategievoorstel is geannuleerd. Er is niets gewijzigd."
            mode = "CLARIFICATION"
            verifier_status = "registry_grounded"
        elif normalize_interaction_mode(interaction_mode) == "CAPABILITY" and terminal_status == "completed":
            # The selector has already chosen and persisted this read-only
            # registry contract; it needs no tools or second provider call.
            content = (
                "Ik kan je helpen om je tradingcontext te begrijpen, ontbrekende informatie zichtbaar te maken "
                "en veilige vervolgstappen voor te bereiden."
            )
            mode = "CAPABILITY"
            verifier_status = "registry_grounded"
        elif terminal_status == "clarification_required":
            clarification = orchestrator.get("selected_clarification") or {}
            content = str(clarification.get("question") or "").strip()
            draft = dict(setup_draft or {})
            if not content and draft.get("operation_id") in {
                "create_setup", "create_strategy", "create_bot"
            }:
                from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
                from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry

                content = FinnV2OperationStateService.clarification_question(
                    draft.get("requested_slot"),
                    contract=FinnV2OperationRegistry().require_supported(draft["operation_id"]),
                    collected_inputs=dict(draft.get("supplied_inputs") or {}),
                )
            content = content or "FINN heeft eerst een verduidelijking nodig."
            mode = "CLARIFICATION"
        elif terminal_status == "rejected":
            content = "FINN heeft de response veilig afgewezen omdat de verificatie faalde."
            mode = "UNAVAILABLE"
            verifier_status = "failed"
        elif terminal_status == "unavailable":
            content = "FINN kon geen betrouwbare response afronden met de beschikbare of geldige context."
            mode = "UNAVAILABLE"
        elif terminal_status == "downgraded":
            verifier_status = "downgraded"
        return {
            "mode": mode,
            "content": content,
            "response_source": "v2_runtime",
            "verifier_status": verifier_status,
            "evidence": [],
            "uncertainty": reason_codes or [str(delivery_envelope.get("status") or terminal_status)],
            "proposal_id": None,
            "confirmation_required": False,
            "next_step": None,
            "reasoning_provenance": reasoning_result.get("reasoning_provenance") or {},
        }

    async def fail_run(
        self,
        *,
        run_id: str,
        user_id: int,
        error_code: str,
        error_message: str,
        retryable: bool = False,
        failure_stage: str = "run_failure",
        primary_exception: Optional[Exception] = None,
    ) -> None:
        if primary_exception is not None or self._session_requires_rollback():
            await self._rollback_failed_session(
                run_id=run_id,
                user_id=user_id,
                failure_stage=failure_stage,
                primary_exception=primary_exception,
            )
        lifecycle: Optional[asyncio.Task[None]] = None
        selection_waiter: Optional[asyncio.Task[bool]] = None
        try:
            response_json = self._terminal_placeholder_response(
                interaction_mode="UNAVAILABLE",
                terminal_status="failed",
                orchestrator={}, verifier={}, reasoning={}, delivery_envelope={},
            )
            contract = await self.runtime_contracts.materialize_terminal(
                run_id=run_id, status="failed", mode="UNAVAILABLE", response=response_json, error_code=error_code
            )
            response_json["_runtime_contract_projection"] = contract.terminal_projection_json
            await self.persist_transition(
                run_id,
                user_id,
                next_status="failed",
                error_code=error_code,
                error_message=error_message,
                retryable=retryable,
                response_json=response_json,
                response_source="foundation_placeholder",
            )
        except Exception as cleanup_exc:
            logger.exception(
                "FINN V2 fail_run cleanup failure",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": failure_stage,
                    "service": "FinnV2RunService",
                    "method": "fail_run",
                    "primary_exception_class": primary_exception.__class__.__name__ if primary_exception else None,
                    "primary_exception_message": str(primary_exception) if primary_exception else None,
                    "cleanup_exception_class": cleanup_exc.__class__.__name__,
                    "cleanup_exception_message": str(cleanup_exc),
                },
            )
            raise

    async def terminalize_unavailable(self, *, run_id: str, user_id: int, error_code: str) -> None:
        response_json = self._terminal_placeholder_response(
            interaction_mode="UNAVAILABLE",
            terminal_status="unavailable",
            orchestrator={}, verifier={}, reasoning={}, delivery_envelope={},
        )
        contract = await self.runtime_contracts.materialize_terminal(
            run_id=run_id, status="unavailable", mode="UNAVAILABLE", response=response_json, error_code=error_code
        )
        response_json["_runtime_contract_projection"] = contract.terminal_projection_json
        await self.persist_transition(
            run_id, user_id, next_status="unavailable", interaction_mode="UNAVAILABLE",
            error_code=error_code, response_json=response_json, response_source="v2_runtime",
        )

    async def cancel_run(self, *, run_id: str, user_id: int):
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        response_json = self._terminal_placeholder_response(
            interaction_mode="UNAVAILABLE", terminal_status="unavailable", orchestrator={}, verifier={}, reasoning={}, delivery_envelope={}
        )
        contract = await self.runtime_contracts.materialize_terminal(
            run_id=run_id, status="canceled", mode="UNAVAILABLE", response=response_json, error_code="run_canceled"
        )
        response_json["_runtime_contract_projection"] = contract.terminal_projection_json
        await self.persist_transition(
            run_id,
            user_id,
            next_status="canceled",
            response_json=response_json,
            response_source="foundation_placeholder",
        )

    async def run_foundation_lifecycle(self, *, run_id: str, user_id: int) -> None:
        await self.persist_transition(run_id, user_id, next_status="queued", response_source="foundation_placeholder")
        await self.persist_transition(run_id, user_id, next_status="collecting", response_source="foundation_placeholder")
        await self.persist_transition(run_id, user_id, next_status="planned", response_source="foundation_placeholder")
        try:
            run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
            if run is None:
                raise LookupError("FINN V2 run not found")
            if self._is_visible_run(run) or self.tools.flags.should_run_block4_shadow(user_id):
                await self.orchestrator.execute_run(run_id=run_id, user_id=user_id, trace_id=run.trace_id)
                await self.complete_run(
                    run_id=run_id,
                    user_id=user_id,
                    phase_outcome=self.orchestrator.consume_phase_outcome(),
                )
            else:
                await self.tools.execute_shadow_tool_chain(run_id=run_id, user_id=user_id)
                await self.complete_run(
                    run_id=run_id,
                    user_id=user_id,
                    phase_outcome=LifecyclePhaseOutcome(
                        terminal_status="completed",
                        interaction_mode="UNAVAILABLE",
                        orchestrator_result_id="shadow-foundation",
                    ),
                )
        except asyncio.CancelledError:
            logger.warning(
                "FINN V2 lifecycle canceled before terminal persistence",
                extra={"run_id": run_id, "user_id": user_id},
            )
            raise
        except Exception as exc:
            logger.exception(
                "FINN V2 lifecycle primary failure",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": "run_foundation_lifecycle",
                    "service": "FinnV2RunService",
                    "method": "run_foundation_lifecycle",
                    "primary_exception_class": exc.__class__.__name__,
                    "primary_exception_message": str(exc),
                },
            )
            await self.fail_run(
                run_id=run_id,
                user_id=user_id,
                error_code="orchestrator_failed",
                error_message=str(exc),
                retryable=False,
                failure_stage="run_foundation_lifecycle",
                primary_exception=exc,
            )

    @classmethod
    async def run_foundation_lifecycle_owned(cls, *, run_id: str, user_id: int) -> None:
        """Run each lifecycle boundary in a fresh database unit of work.

        The coordinator only exchanges immutable ids and a typed phase outcome
        between sessions. ORM instances must never survive a rollback boundary.
        """
        selector_started = asyncio.Event()
        selection_ready = asyncio.Event()
        flags = FinnV2FlagService()
        lifecycle: asyncio.Task | None = None
        selector_started_waiter: asyncio.Task | None = None
        selection_waiter: asyncio.Task | None = None
        lifecycle_released = asyncio.Event()

        async def _run_owned_lifecycle() -> None:
            try:
                # Reuse one short-lived session for the initial lifecycle
                # transitions. Opening three production connections in series
                # consumed most of the interactive deadline before selection.
                async with async_session_factory() as session:
                    transition_service = cls(session)
                    for status in ("queued", "collecting", "planned"):
                        await transition_service.persist_transition(
                            run_id,
                            user_id,
                            next_status=status,
                            response_source="foundation_placeholder",
                        )

                async with async_session_factory() as session:
                    service = cls(session)
                    run = await service.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
                    if run is None:
                        raise LookupError("FINN V2 run not found")
                    visible = service._is_visible_run(run)
                    run_shadow = service.tools.flags.should_run_block4_shadow(user_id)

                prepared: FinnResponsesFrontDoorResult | None = None
                if visible:
                    from backend.services.ai_usage_observability_service import ai_usage_context

                    with ai_usage_context(entry_point="finn_v2_responses", user_id=user_id):
                        prepared, message = await cls.prepare_responses_turn(
                            run_id=run_id, user_id=user_id,
                            selector_started=selector_started,
                            selection_ready=selection_ready,
                        )
                        if prepared.proposal_analysis is None:
                            answer = await FinnResponsesAnswerVerifier(client=openai_client.async_client).verify(
                                message=message, result=prepared.response,
                                previous_response=prepared.previous_response,
                            )
                            remaining = remaining_lifecycle_seconds()
                            if (
                                answer.reason == "responses_evidence_not_verified"
                                and any(
                                    str(call.get("name") or "").startswith("get_")
                                    for call in prepared.response.tool_trace
                                )
                                and (remaining is None or remaining > 12)
                            ):
                                prepared, message = await cls.prepare_responses_turn(
                                    run_id=run_id, user_id=user_id,
                                    selector_started=selector_started,
                                    selection_ready=selection_ready,
                                    recovery_response_id=prepared.response.response_id,
                                    prior_tool_trace=prepared.response.tool_trace,
                                )
                                answer = (
                                    None if prepared.proposal_analysis is not None
                                    else await FinnResponsesAnswerVerifier(client=openai_client.async_client).verify(
                                        message=message, result=prepared.response,
                                        previous_response=prepared.previous_response,
                                    )
                                )
                        else:
                            answer = None
                    if answer is not None:
                        async with async_session_factory() as session:
                            await cls(session).complete_responses_read(
                                run_id=run_id, user_id=user_id,
                                response_id=prepared.response.response_id,
                                answer=answer,
                                previous_response=prepared.previous_response,
                            )
                        return

                async with async_session_factory() as session:
                    service = cls(session)
                    run = await service.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
                    if run is None:
                        raise LookupError("FINN V2 run not found")
                    trace_id = run.trace_id

                    async def transition_phase(**kwargs) -> None:
                        async with async_session_factory() as transition_session:
                            await cls(transition_session).persist_transition(**kwargs)

                    if visible or run_shadow:
                        async def selection_persisted() -> None:
                            selection_ready.set()

                        async def selector_phase_started() -> None:
                            selector_started.set()

                        orchestrator = FinnV2OrchestratorService(
                            session,
                            phase_transition=transition_phase,
                            selector_started=selector_phase_started,
                            selection_persisted=selection_persisted,
                        )
                        await orchestrator.execute_run(
                            run_id=run_id, user_id=user_id, trace_id=trace_id,
                            analysis_override=prepared.proposal_analysis if prepared else None,
                        )
                        # The orchestrator has committed every persistence
                        # boundary it owns. Do not refresh the original ORM
                        # instance here: in production that defensive read
                        # could wait behind an active polling transaction and
                        # consume the terminal reserve after a proposal was
                        # already durable. The terminal writer validates the
                        # persisted status again in its fresh session.
                        if is_terminal_status(run.status):
                            logger.info(
                                "FINN V2 lifecycle stopped after an external terminal transition",
                                extra={"run_id": run_id, "user_id": user_id, "status": run.status},
                            )
                            return
                        phase_outcome = orchestrator.consume_phase_outcome()
                    else:
                        # Shadow-only runs have no selector boundary, so they do
                        # not participate in the visible-run selector watchdog.
                        selection_ready.set()
                        await service.tools.execute_shadow_tool_chain(run_id=run_id, user_id=user_id)
                        phase_outcome = LifecyclePhaseOutcome(
                            terminal_status="completed",
                            interaction_mode="UNAVAILABLE",
                            orchestrator_result_id="shadow-foundation",
                        )

                async with async_session_factory() as session:
                    await cls(session).complete_run(
                        run_id=run_id,
                        user_id=user_id,
                        phase_outcome=phase_outcome,
                        responses_response_id=prepared.response.response_id if prepared else None,
                    )
            finally:
                # A deadline terminalizer takes a fresh database unit of work.
                # Signal only after every owned session has left its context so
                # it can never contend with the cancelled lifecycle's locks.
                lifecycle_released.set()

        async def _cancel_lifecycle_within_reserve() -> None:
            """Request cancellation without letting cleanup consume the SLA.

            ``asyncio.wait_for`` waits for a cancelled task to acknowledge
            cancellation.  A provider thread or database cleanup can take
            longer than the visible lifecycle deadline, so that behaviour
            previously delayed the typed terminal projection and blocked the
            dedicated interactive worker.  The lifecycle is cancellation-safe;
            terminalisation always happens below in a fresh unit of work.
            """
            if lifecycle is None:
                return
            if lifecycle.done():
                with suppress(asyncio.CancelledError, Exception):
                    lifecycle.result()
                return
            lifecycle.cancel()
            release_waiter = asyncio.create_task(lifecycle_released.wait())
            done, _ = await asyncio.wait(
                {lifecycle, release_waiter},
                timeout=min(1.0, flags.terminal_persistence_reserve_seconds()),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if release_waiter not in done:
                release_waiter.cancel()
                with suppress(asyncio.CancelledError):
                    await release_waiter
            if not lifecycle.done():
                logger.warning(
                    "FINN V2 lifecycle cancellation did not release its session within the bounded reserve",
                    extra={"run_id": run_id, "user_id": user_id},
                )
            else:
                with suppress(asyncio.CancelledError, Exception):
                    lifecycle.result()

        try:
            # Context hydration, selector, and post-selection work have
            # separate budgets.  The provider watchdog begins only after
            # context hydration has completed and the selector is about to
            # issue its bounded call.
            # terminal reserve is included only after the persisted selector
            # transition, so a slow but valid selector cannot cancel that
            # transition before its immutable intent reaches the contract.
            deadline = monotonic() + flags.lifecycle_deadline_seconds()
            lifecycle_budget_token = set_lifecycle_deadline(deadline)
            # ``create_task`` snapshots the context variable, keeping this
            # deadline attached to provider work even after the coordinator
            # resumes to watch for terminalisation.
            lifecycle = asyncio.create_task(_run_owned_lifecycle())
            selector_started_waiter = asyncio.create_task(selector_started.wait())
            selection_waiter = asyncio.create_task(selection_ready.wait())
            # One absolute budget prevents a selector allowance followed by a
            # fresh lifecycle allowance from exceeding the visible-run SLA.
            # The reserve remains available only for terminal persistence.
            def _remaining(*, reserve: bool = False) -> float:
                remaining = deadline - monotonic()
                if reserve:
                    remaining -= flags.terminal_persistence_reserve_seconds()
                return max(0.1, remaining)

            done, _ = await asyncio.wait(
                {lifecycle, selector_started_waiter},
                timeout=_remaining(),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if lifecycle in done:
                # Surface pre-selection failures directly instead of waiting
                # until the selector watchdog expires.
                await lifecycle
            if selector_started_waiter not in done:
                raise asyncio.TimeoutError()
            await selector_started_waiter
            await asyncio.wait_for(
                selection_waiter,
                timeout=min(flags.selector_phase_deadline_seconds(), _remaining(reserve=True)),
            )
            # Do not use ``wait_for`` here. It waits indefinitely for a task
            # that is slow to acknowledge cancellation, which defeats the
            # terminal reserve and can starve every following interactive run.
            done, _ = await asyncio.wait(
                {lifecycle},
                timeout=_remaining(reserve=True),
                return_when=asyncio.ALL_COMPLETED,
            )
            if lifecycle not in done:
                if lifecycle.done():
                    await lifecycle
                raise asyncio.TimeoutError()
            await lifecycle
        except FinnResponsesError as exc:
            await _cancel_lifecycle_within_reserve()
            async with async_session_factory() as session:
                await cls(session).terminalize_unavailable(
                    run_id=run_id, user_id=user_id, error_code=str(exc),
                )
            selection_ready.set()
        except asyncio.TimeoutError as exc:
            await _cancel_lifecycle_within_reserve()
            logger.warning(
                "FINN V2 owned lifecycle reached terminal deadline",
                extra={"run_id": run_id, "user_id": user_id},
            )
            async with async_session_factory() as session:
                service = cls(session)
                if selection_waiter is not None and not selection_waiter.done():
                    await service.terminalize_unavailable(
                        run_id=run_id, user_id=user_id, error_code="selector_phase_timeout"
                    )
                else:
                    await service.fail_run(
                        run_id=run_id,
                        user_id=user_id,
                        error_code="lifecycle_deadline_exceeded",
                        error_message="FINN kon deze aanvraag niet binnen de veilige verwerkingstijd afronden.",
                        retryable=False,
                        failure_stage="run_foundation_lifecycle_deadline",
                        primary_exception=exc,
                    )
        except asyncio.CancelledError:
            await _cancel_lifecycle_within_reserve()
            raise
        except Exception as exc:
            await _cancel_lifecycle_within_reserve()
            logger.exception(
                "FINN V2 owned lifecycle primary failure",
                extra={"run_id": run_id, "user_id": user_id, "primary_exception": str(exc)},
            )
            async with async_session_factory() as session:
                await cls(session).fail_run(
                    run_id=run_id,
                    user_id=user_id,
                    error_code="orchestrator_failed",
                    error_message=str(exc),
                    retryable=False,
                    failure_stage="run_foundation_lifecycle_owned",
                    primary_exception=exc,
                )
        finally:
            if "lifecycle_budget_token" in locals():
                reset_lifecycle_deadline(lifecycle_budget_token)
            if selector_started_waiter is not None and not selector_started_waiter.done():
                selector_started_waiter.cancel()
                with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await selector_started_waiter
            if selection_waiter is not None and not selection_waiter.done():
                selection_waiter.cancel()
                with suppress(asyncio.CancelledError, asyncio.TimeoutError):
                    await selection_waiter

    def _is_visible_run(self, run) -> bool:
        return getattr(run, "visibility", None) == "visible" or getattr(run, "feature_mode", None) == "visible_readonly"

    async def apply_retention(self, *, message_days: int, trace_days: int) -> Dict[str, int]:
        now = datetime.now(timezone.utc)
        message_cutoff = now - timedelta(days=message_days)
        trace_cutoff = now - timedelta(days=trace_days)
        redacted = await self.runs.redact_messages_older_than(message_cutoff)
        deleted = await self.runs.delete_traces_older_than(trace_cutoff)
        tool_retention = await self.tools.apply_retention()
        logger.info(
            "FINN V2 retention cleanup completed.",
            extra={"message_redacted": redacted, "traces_deleted": deleted, **tool_retention},
        )
        return {"messages_redacted": redacted, "traces_deleted": deleted, **tool_retention}

    async def envelope_from_run(self, run) -> AgentRunStatusEnvelope:
        response_payload = dict(run.response_json or {})
        # Terminal delivery metadata is projected once when the run completes.
        # Polling and SSE can then serve the same envelope without reopening the
        # full verifier/evidence chain for every client poll.
        runtime_trace: Dict[str, Any] = dict(response_payload.pop("_runtime_trace", {}) or {})
        if is_terminal_status(run.status):
            contract = await self.runtime_contracts.get_for_run(run_id=run.id)
            if contract is not None:
                projection = dict(contract.terminal_projection_json or {})
                if projection:
                    response_payload = dict(projection.get("response") or response_payload)
                    runtime_trace = projection
                else:
                    runtime_trace = {
                        "projection_version": getattr(contract, "contract_version", "unknown"),
                        "contract_id": contract.contract_id,
                        "run_id": run.id,
                        "conversation_id": run.conversation_id,
                        "terminal_status": run.status,
                        "terminal_response_type": "failure",
                        "error_code": "runtime_contract_terminal_projection_missing",
                    }
        try:
            if response_payload:
                response_payload["mode"] = normalize_interaction_mode(response_payload.get("mode"))
            envelope_mode = normalize_interaction_mode(run.interaction_mode) if run.interaction_mode else None
        except FinnV2ModeContractError as exc:
            runtime_trace["mode_contract_error"] = {"code": exc.code, "mode": exc.mode}
            response_payload = {
                "mode": "UNAVAILABLE",
                "content": "Deze FINN-run bevat een incompatibel historisch responsecontract.",
                "response_source": "v2_runtime",
                "verifier_status": "failed",
                "evidence": [],
                "uncertainty": [exc.code],
                "proposal_id": None,
                "confirmation_required": False,
            }
            envelope_mode = "UNAVAILABLE"
        else:
            if is_terminal_status(run.status) and not runtime_trace:
                # Historical runs predate the compact terminal projection. Keep
                # them readable without turning high-frequency polling into a
                # fan-out of artifact queries.
                runtime_trace = {
                    "delivery": {"status": run.status, "response_source": "v2_runtime"},
                    "policy": {"allowed": (run.policy_json or {}).get("allowed")},
                    "terminal_projection": "legacy_compact",
                }
        response = VerifiedResponse(**response_payload) if response_payload else None
        policy = PolicyDecision(**run.policy_json) if run.policy_json else None
        return AgentRunStatusEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=run.status,
            mode=envelope_mode,
            visibility=run.visibility,
            response=response,
            policy=policy,
            created_at=run.created_at,
            updated_at=run.updated_at,
            completed_at=run.completed_at,
            error_code=run.error_code or runtime_trace.get("mode_contract_error", {}).get("code"),
            error_message=run.error_message or ("FINN V2 mode contract is invalid." if runtime_trace.get("mode_contract_error") else None),
            retryable=bool(run.retryable),
            runtime_trace=runtime_trace,
        )

    def _terminal_runtime_trace(
        self,
        artifacts: Dict[str, Any],
        *,
        runtime_contract: Optional[Dict[str, Any]] = None,
        projection_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project persisted records for polling/SSE without exposing evidence data."""
        orchestrator = artifacts.get("orchestrator_result") or {}
        reasoning = artifacts.get("reasoning_result") or {}
        reasoning_result = reasoning.get("result") or {}
        verifier = artifacts.get("verifier_result") or {}
        validation = artifacts.get("validation_result") or {}
        verified = artifacts.get("verified_response") or {}
        delivery = artifacts.get("delivery_envelope") or {}
        policy = artifacts.get("policy_result") or {}
        request_plan = dict(orchestrator.get("tool_plan") or {}).get("request_plan") or {}
        reasoning_provenance = dict(reasoning_result.get("reasoning_provenance") or {})
        reasoning_provenance.setdefault("operation_id", request_plan.get("operation_id"))
        projection = dict(runtime_contract or {})
        contract = projection or {
            "initial_operation_id": request_plan.get("initial_operation_id") or request_plan.get("operation_id"),
            "final_operation_id": request_plan.get("operation_id"),
            "operation_change_reason": request_plan.get("operation_change_reason"),
            "target_source": request_plan.get("target_asset_source"),
            "conversation_reference": request_plan.get("conversation_reference"),
        }
        return {
            "contract": {
                "initial_operation_id": contract.get("initial_operation_id"),
                "final_operation_id": contract.get("final_operation_id"),
                "operation_change_reason": contract.get("operation_change_reason"),
                "target_asset_source": contract.get("target_source") or request_plan.get("target_asset_source"),
                "conversation_reference": contract.get("conversation_reference"),
            },
            "terminal_projection": projection or None,
            "terminal_projection_hash": projection_hash,
            "requested_mode": orchestrator.get("interaction_mode"),
            "delivery": {
                "status": delivery.get("status"),
                "verified_response_id": verified.get("verified_response_id"),
                "response_source": "v2_runtime",
            },
            "orchestrator": {
                "orchestrator_result_id": orchestrator.get("orchestrator_result_id"),
                "required_domains": orchestrator.get("required_domains") or [],
                "optional_domains": orchestrator.get("optional_domains") or [],
                "outcome": orchestrator.get("outcome"),
                "snapshot_id": orchestrator.get("snapshot_id"),
                "validation_id": orchestrator.get("validation_id"),
            },
            "policy": {
                "allowed": policy.get("allowed"),
                "policy_class": policy.get("policy_class"),
            },
            "validation": {
                "integrity_status": validation.get("integrity_status"),
                "validation_id": validation.get("validation_id"),
            },
            "reasoning": {
                "reasoning_result_id": reasoning.get("reasoning_result_id"),
                "status": reasoning.get("status"),
                "mode": reasoning.get("mode"),
                "model": reasoning.get("model"),
                "latency_ms": reasoning.get("latency_ms"),
                "error_codes": reasoning.get("error_codes") or [],
                "provenance": reasoning_provenance,
            },
            "verifier": {
                "verifier_result_id": verifier.get("verifier_result_id"),
                "passed": verifier.get("passed"),
                "action": verifier.get("action"),
                "reason_codes": verifier.get("reason_codes") or [],
                "coverage": verifier.get("coverage") or {},
            },
            "tool_calls": artifacts.get("tool_calls") or [],
            "evidence_references": artifacts.get("evidence_references") or [],
        }

    def _trace_payload(self, run, *, status: str, response_source: Optional[str]) -> Dict[str, Any]:
        return {
            "run_id": run.id,
            "conversation_id": run.conversation_id,
            "user_id": run.user_id,
            "transport": run.transport,
            "visibility": run.visibility,
            "feature_mode": run.feature_mode,
            "status": status,
            "request_path": getattr(run, "request_path", None) or (run.client_context_json or {}).get("_request_path"),
            "trace_id": run.trace_id,
            "response_source": response_source,
        }

    def _session_requires_rollback(self) -> bool:
        sync_session = getattr(self.session, "sync_session", None)
        if sync_session is not None and getattr(sync_session, "is_active", True) is False:
            return True
        try:
            transaction = self.session.get_transaction()
        except NotImplementedError:
            transaction = getattr(sync_session, "get_transaction", lambda: None)()
        return bool(transaction is not None and getattr(transaction, "is_active", True) is False)

    async def _rollback_failed_session(
        self,
        *,
        run_id: str,
        user_id: int,
        failure_stage: str,
        primary_exception: Optional[Exception],
    ) -> None:
        try:
            await self.session.rollback()
        except Exception as cleanup_exc:
            logger.exception(
                "FINN V2 rollback before fail_run failed",
                extra={
                    "run_id": run_id,
                    "user_id": user_id,
                    "failure_stage": failure_stage,
                    "service": "FinnV2RunService",
                    "method": "_rollback_failed_session",
                    "primary_exception_class": primary_exception.__class__.__name__ if primary_exception else None,
                    "primary_exception_message": str(primary_exception) if primary_exception else None,
                    "cleanup_exception_class": cleanup_exc.__class__.__name__,
                    "cleanup_exception_message": str(cleanup_exc),
                },
            )
            raise

    async def _commit_session_if_possible(self) -> None:
        commit = getattr(self.session, "commit", None)
        if commit is not None:
            await commit()
