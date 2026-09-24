"""Model-driven FINN entrypoint before the existing action safety pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from typing import Any, Mapping

from backend.services.asset_catalog_service import mentioned_catalog_symbols, resolve_catalog_symbol
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_orchestrator_schema import RequestAnalysisResult
from backend.services.finn_v2_operation_state_service import FinnV2OperationStateService
from backend.services.finn_v2_responses_loop import FinnResponsesError, FinnResponsesLoop, FinnResponsesResult
from backend.services.finn_v2_responses_proposal_selection import FinnResponsesProposalSelection
from backend.services.finn_v2_responses_read_executor import FinnResponsesReadExecutor
from backend.services.finn_v2_responses_tool_catalog import FinnResponsesToolCall
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService


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

    async def run(
        self,
        *,
        message: str,
        instructions: str,
        conversation_context: Mapping[str, object],
        verified_asset: str | None,
        previous_response_id: str | None = None,
        previous_response: dict[str, Any] | None = None,
    ) -> FinnResponsesFrontDoorResult:
        selected: RequestAnalysisResult | None = None
        read_context: list[dict[str, Any]] = []
        pending_operation = FinnV2OperationStateService.pending_operation_id(conversation_context)
        target_retry_used = False

        async def execute(call: FinnResponsesToolCall) -> dict[str, Any]:
            nonlocal selected, target_retry_used
            if call.operation_id is None:
                model_asset = call.inputs.get("asset")
                if model_asset:
                    symbol = resolve_catalog_symbol(model_asset)
                    if symbol not in mentioned_catalog_symbols(message):
                        call = replace(call, inputs={key: value for key, value in call.inputs.items() if key != "asset"})
                    else:
                        call = replace(call, inputs={**call.inputs, "asset": symbol})
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
        ).run(
            message=message,
            instructions=instructions,
            previous_response_id=previous_response_id,
            guided_operation_id=pending_operation,
        )
        if pending_operation and selected is None:
            raise FinnResponsesError("guided_proposal_tool_call_required")
        recent_action_result = dict(conversation_context.get("previous_action_result") or {})
        if recent_action_result.get("owner_user_id") != self.user_id or recent_action_result.get("result_status") != "succeeded":
            recent_action_result = {}
        return FinnResponsesFrontDoorResult(result, selected, previous_response, recent_action_result or None)
