from __future__ import annotations

from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_contract import is_terminal_status
from backend.infrastructure.repositories.finn_v2_orchestrator_repository import FinnV2OrchestratorRepository
from backend.infrastructure.repositories.finn_v2_evidence_repository import FinnV2EvidenceRepository
from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.infrastructure.repositories.finn_v2_reasoning_repository import FinnV2ReasoningRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_tool_call_repository import FinnV2ToolCallRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.infrastructure.repositories.finn_v2_verifier_repository import FinnV2VerifierRepository
from backend.infrastructure.repositories.finn_v2_verified_response_repository import FinnV2VerifiedResponseRepository
from backend.schemas.finn_v2_orchestrator_schema import ORCHESTRATOR_VERSION
from backend.schemas.finn_v2_policy_schema import POLICY_VERSION
from backend.schemas.finn_v2_reasoning_schema import PersistedReasoningRecord, ReasoningResult
from backend.schemas.finn_v2_delivery_schema import FinnV2DeliveryEnvelope, FinnV2StreamEvent
from backend.schemas.finn_v2_response_schema import VerifiedResponse


class FinnV2DeliveryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.runs = FinnV2RunRepository(session)
        self.orchestrators = FinnV2OrchestratorRepository(session)
        self.policies = FinnV2PolicyRepository(session)
        self.reasoning = FinnV2ReasoningRepository(session)
        self.snapshots = FinnV2StateRepository(session)
        self.tool_calls = FinnV2ToolCallRepository(session)
        self.evidence = FinnV2EvidenceRepository(session)
        self.validations = FinnV2ValidationRepository(session)
        self.verifiers = FinnV2VerifierRepository(session)
        self.verified = FinnV2VerifiedResponseRepository(session)

    async def get_delivery_envelope(self, *, user_id: int, run_id: str) -> FinnV2DeliveryEnvelope:
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        row = await self.verified.get_latest_for_run(run_id=run_id, user_id=user_id)
        response = VerifiedResponse.parse_obj(row.response_json) if row is not None else None
        status = "completed" if response is not None else run.status
        return FinnV2DeliveryEnvelope(
            run_id=run.id,
            conversation_id=run.conversation_id,
            status=status,
            response=response,
            proposal_id=response.proposal_id if response is not None else None,
            confirmation_required=bool(response.confirmation_required) if response is not None else False,
            error_code=getattr(run, "error_code", None),
            error_message=getattr(run, "error_message", None),
        )

    async def stream_delivery_events(self, *, user_id: int, run_id: str) -> AsyncIterator[FinnV2StreamEvent]:
        envelope = await self.get_delivery_envelope(user_id=user_id, run_id=run_id)
        if envelope.response is not None:
            yield FinnV2StreamEvent(
                event="run.completed",
                run_id=run_id,
                payload={"response": envelope.response.dict(), "delivery_source": envelope.delivery_source},
            )
            return
        if not is_terminal_status(envelope.status):
            yield FinnV2StreamEvent(
                event="run.progress",
                run_id=run_id,
                payload={"delivery_source": envelope.delivery_source, "status": envelope.status},
            )
            return
        yield FinnV2StreamEvent(
            event=f"run.{envelope.status}",
            run_id=run_id,
            payload={"delivery_source": envelope.delivery_source, "status": envelope.status},
        )

    async def get_delivery_artifacts(self, *, user_id: int, run_id: str) -> dict:
        envelope = await self.get_delivery_envelope(user_id=user_id, run_id=run_id)
        run = await self.runs.get_by_id_for_user(run_id=run_id, user_id=user_id)
        if run is None:
            raise LookupError("FINN V2 run not found")
        orchestrator = await self.orchestrators.get_for_run_version(
            run_id=run_id,
            user_id=user_id,
            orchestrator_version=ORCHESTRATOR_VERSION,
        )
        policy = await self.policies.get_for_run_version(
            run_id=run_id,
            user_id=user_id,
            policy_version=POLICY_VERSION,
        )
        verified_row = await self.verified.get_latest_for_run(run_id=run_id, user_id=user_id)
        verifier = None
        if verified_row is not None and getattr(verified_row, "verifier_result_id", None):
            verifier = await self.verifiers.get_by_id_for_user(
                verifier_result_id=verified_row.verifier_result_id,
                user_id=user_id,
            )
        if verifier is None:
            verifier = await self.verifiers.get_latest_for_run(run_id=run_id, user_id=user_id)
        reasoning = None
        snapshot = None
        validation = None
        if verifier is not None and getattr(verifier, "reasoning_result_id", None):
            reasoning_row = await self.reasoning.get_by_id_for_user(
                reasoning_result_id=verifier.reasoning_result_id,
                user_id=user_id,
            )
            if reasoning_row is not None:
                reasoning = PersistedReasoningRecord(
                        reasoning_result_id=reasoning_row.id,
                        run_id=reasoning_row.run_id,
                        user_id=reasoning_row.user_id,
                        orchestrator_result_id=reasoning_row.orchestrator_result_id,
                        policy_decision_id=reasoning_row.policy_decision_id,
                        snapshot_id=reasoning_row.snapshot_id,
                        validation_id=reasoning_row.validation_id,
                        status=reasoning_row.status,
                        mode=reasoning_row.mode,
                        context_version=reasoning_row.context_version,
                        evidence_set_hash=reasoning_row.evidence_set_hash,
                        input_hash=reasoning_row.input_hash,
                        prompt_version=reasoning_row.prompt_version,
                        schema_version=reasoning_row.schema_version,
                        reasoning_version=reasoning_row.reasoning_version,
                        model=reasoning_row.model,
                        result=ReasoningResult.parse_obj(reasoning_row.result_json) if reasoning_row.result_json else None,
                        error_codes=reasoning_row.error_codes_json,
                        input_tokens=reasoning_row.input_tokens,
                        output_tokens=reasoning_row.output_tokens,
                        reasoning_tokens=reasoning_row.reasoning_tokens,
                        latency_ms=reasoning_row.latency_ms,
                        retry_count=reasoning_row.retry_count,
                        created_at=reasoning_row.created_at,
                        completed_at=reasoning_row.completed_at,
                )
                snapshot = await self.snapshots.get_by_id_for_user(
                    snapshot_id=reasoning_row.snapshot_id,
                    user_id=user_id,
                )
                validation = await self.validations.get_by_id_for_user(
                    validation_id=reasoning_row.validation_id,
                    user_id=user_id,
                )
        tool_calls = await self.tool_calls.list_for_run(run_id=run_id, user_id=user_id)
        evidence = await self.evidence.list_for_run(run_id=run_id, user_id=user_id)
        return {
            "run": run,
            "delivery_envelope": envelope.dict(),
            "verified_response": envelope.response.dict() if envelope.response is not None else None,
            "orchestrator_result": self._orchestrator_payload(orchestrator),
            "policy_result": getattr(policy, "decision_json", None),
            "reasoning_result": self._reasoning_payload(reasoning),
            "verifier_result": getattr(verifier, "result_json", None),
            "financial_state_snapshot": getattr(snapshot, "snapshot_json", None),
            "validation_result": getattr(validation, "result_json", None),
            "tool_calls": [self._tool_call_payload(row) for row in tool_calls],
            "evidence_references": [self._evidence_reference_payload(row) for row in evidence],
        }

    def _orchestrator_payload(self, row) -> Optional[dict]:
        if row is None:
            return None
        return {
            "orchestrator_result_id": row.id,
            "run_id": row.run_id,
            "interaction_mode": row.interaction_mode,
            "subject_scopes": row.subject_scopes_json,
            "required_domains": row.required_domains_json,
            "optional_domains": row.optional_domains_json,
            "tool_plan": row.tool_plan_json,
            "snapshot_id": row.snapshot_id,
            "validation_id": row.validation_id,
            "outcome": row.outcome,
            "selected_clarification": row.selected_clarification_json,
            "unavailable_codes": row.unavailable_codes_json,
            "uncertainty_codes": row.uncertainty_codes_json,
            "orchestrator_version": row.orchestrator_version,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _reasoning_payload(self, record: Optional[PersistedReasoningRecord]) -> Optional[dict]:
        if record is None:
            return None
        payload = record.dict()
        if record.result is not None:
            payload["result"] = record.result.dict()
        return payload

    def _tool_call_payload(self, row) -> dict:
        return {
            "tool_call_id": row.id,
            "tool_name": row.tool_name,
            "status": row.status,
            "selector": row.selector_json,
            "result_summary": row.result_summary_json,
            "error_codes": row.error_codes_json,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        }

    def _evidence_reference_payload(self, row) -> dict:
        """Expose provenance only; artifact payloads remain server-side."""
        return {
            "artifact_id": row.id,
            "tool_call_id": row.tool_call_id,
            "tool_name": row.tool_name,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "asset": row.asset,
            "source": row.source,
            "freshness": row.freshness,
            "availability": row.availability,
            "user_scoped": bool(row.user_scoped),
        }
