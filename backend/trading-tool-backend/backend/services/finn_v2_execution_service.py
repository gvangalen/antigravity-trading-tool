from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_execution_repository import FinnV2ExecutionRepository
from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import FinnV2RuntimeContractRepository
from backend.schemas.finn_v2_execution_schema import ExecutionResult
from backend.schemas.finn_v2_policy_schema import StepUpProof
from backend.services.finn_v2_action_adapter_registry import FinnV2ActionAdapterRegistry
from backend.services.finn_v2_execution_gate_service import FinnV2ExecutionGateService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.platform_metrics import increment_execution_safety_counter, record_latency_sample


class FinnV2ExecutionService:
    def __init__(self, session: AsyncSession, *, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.repo = FinnV2ExecutionRepository(session)
        self.proposals = FinnV2ProposalRepository(session)
        self.runtime_contracts = FinnV2RuntimeContractRepository(session)
        self.gates = FinnV2ExecutionGateService(session, flag_service=self.flags)
        self.adapters = FinnV2ActionAdapterRegistry(session, flag_service=self.flags)

    async def execute(self, *, proposal_id: str, user_id: int, idempotency_key: str, expected_payload_hash: str, step_up_proof: StepUpProof | None = None) -> ExecutionResult:
        existing = await self.repo.get_by_idempotency_key_for_user(idempotency_key=idempotency_key, user_id=user_id)
        if existing is not None:
            return ExecutionResult(
                execution_id=existing.id,
                proposal_id=existing.proposal_id,
                user_id=existing.user_id,
                operation_type=existing.operation_type,
                status="already_executed" if existing.status == "succeeded" else existing.status,
                idempotency_key=existing.idempotency_key,
                precondition_hash=existing.precondition_hash,
                postcondition_hash=existing.postcondition_hash,
                error_codes=existing.error_codes_json,
                started_at=existing.started_at,
                completed_at=existing.completed_at,
            )
        existing_for_proposal = await self.repo.get_for_proposal(proposal_id=proposal_id, user_id=user_id)
        if existing_for_proposal is not None:
            return ExecutionResult(
                execution_id=existing_for_proposal.id,
                proposal_id=existing_for_proposal.proposal_id,
                user_id=existing_for_proposal.user_id,
                operation_type=existing_for_proposal.operation_type,
                status="already_executed" if existing_for_proposal.status == "succeeded" else existing_for_proposal.status,
                idempotency_key=existing_for_proposal.idempotency_key,
                precondition_hash=existing_for_proposal.precondition_hash,
                postcondition_hash=existing_for_proposal.postcondition_hash,
                error_codes=existing_for_proposal.error_codes_json,
                started_at=existing_for_proposal.started_at,
                completed_at=existing_for_proposal.completed_at,
            )
        proposal = await self.proposals.get_by_id_for_user(proposal_id=proposal_id, user_id=user_id)
        if proposal is None:
            raise LookupError("proposal_not_owned")
        if proposal.payload_hash != expected_payload_hash:
            raise ValueError("proposal_payload_hash_mismatch")
        gate = await self.gates.check_execution_eligibility(
            user_id=user_id,
            run_id=proposal.run_id,
            proposal_id=proposal_id,
            step_up_proof=step_up_proof,
        )
        if not gate.eligible:
            gate_payload = to_json_safe(gate.dict())
            execution = await self.repo.create(
                id=f"finn-v2-execution-{uuid.uuid4().hex}",
                proposal_id=proposal_id,
                run_id=proposal.run_id,
                user_id=user_id,
                operation_type=proposal.operation_type,
                status="blocked",
                idempotency_key=idempotency_key,
                precondition_hash=self._hash({"proposal": proposal.payload_json, "gate": gate_payload}),
                postcondition_hash=None,
                result_json=gate_payload,
                error_codes_json=gate.blocking_codes,
                completed_at=datetime.now(timezone.utc),
            )
            increment_execution_safety_counter(f"finn_v2_executions_total:{proposal.operation_type}:blocked")
            await self._record_workflow_event(
                proposal,
                event="execution_blocked",
                execution_id=execution.id,
            )
            return ExecutionResult(
                execution_id=execution.id,
                proposal_id=proposal_id,
                user_id=user_id,
                operation_type=proposal.operation_type,
                status="blocked",
                idempotency_key=idempotency_key,
                precondition_hash=execution.precondition_hash,
                postcondition_hash=None,
                error_codes=execution.error_codes_json,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
            )
        adapter = self.adapters.get(proposal.operation_type)
        if adapter is None:
            raise ValueError("execution_adapter_unavailable")
        started_at = datetime.now(timezone.utc)
        gate_payload = to_json_safe(gate.dict())
        precondition_hash = self._hash({"proposal": proposal.payload_json, "gate": gate_payload})
        execution = await self.repo.create(
            id=f"finn-v2-execution-{uuid.uuid4().hex}",
            proposal_id=proposal_id,
            run_id=proposal.run_id,
            user_id=user_id,
            operation_type=proposal.operation_type,
            status="started",
            idempotency_key=idempotency_key,
            precondition_hash=precondition_hash,
            result_json=None,
            error_codes_json=[],
            started_at=started_at,
        )
        try:
            result_payload = await adapter(user_id, proposal.payload_json)
            # Adapters expose existing domain-service results. Normalize them at
            # the execution boundary so values such as Decimal are safe for the
            # persisted JSONB result and its deterministic postcondition hash.
            safe_result_payload = to_json_safe(result_payload)
            postcondition_hash = await self.adapters.postcondition_hash(
                proposal.operation_type,
                user_id=user_id,
                payload=safe_result_payload,
            )
            execution.status = "succeeded"
            execution.postcondition_hash = postcondition_hash
            execution.result_json = safe_result_payload
            execution.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
            await self.runtime_contracts.record_action_result(
                run_id=proposal.run_id,
                action_result=self._action_result(proposal=proposal, execution=execution, result=safe_result_payload),
            )
            record_latency_sample(f"finn_v2_execution_latency_ms:{proposal.operation_type}", int((execution.completed_at - started_at).total_seconds() * 1000))
            increment_execution_safety_counter(f"finn_v2_executions_total:{proposal.operation_type}:succeeded")
            await self._record_workflow_event(
                proposal,
                event="execution_succeeded",
                execution_id=execution.id,
            )
            return ExecutionResult(
                execution_id=execution.id,
                proposal_id=proposal_id,
                user_id=user_id,
                operation_type=proposal.operation_type,
                status="succeeded",
                idempotency_key=idempotency_key,
                precondition_hash=precondition_hash,
                postcondition_hash=postcondition_hash,
                error_codes=[],
                started_at=started_at,
                completed_at=execution.completed_at,
            )
        except Exception as exc:
            execution.status = "failed"
            execution.error_codes_json = [str(exc)]
            execution.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
            increment_execution_safety_counter(f"finn_v2_executions_total:{proposal.operation_type}:failed")
            await self._record_workflow_event(
                proposal,
                event="execution_failed",
                execution_id=execution.id,
            )
            return ExecutionResult(
                execution_id=execution.id,
                proposal_id=proposal_id,
                user_id=user_id,
                operation_type=proposal.operation_type,
                status="failed",
                idempotency_key=idempotency_key,
                precondition_hash=precondition_hash,
                postcondition_hash=None,
                error_codes=[str(exc)],
                started_at=started_at,
                completed_at=execution.completed_at,
            )

    async def _record_workflow_event(self, proposal, *, event: str, execution_id: str) -> None:
        """Mirror a completed workflow step into the safe run projection."""
        await self.runtime_contracts.record_proposal_lifecycle(
            run_id=proposal.run_id,
            proposal_id=proposal.id,
            operation_id=proposal.operation_type,
            payload_hash=proposal.payload_hash,
            event=event,
            execution_id=execution_id,
        )

    def _hash(self, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @staticmethod
    def _action_result(*, proposal, execution, result: dict) -> dict:
        change = dict((proposal.payload_json or {}).get("change") or {})
        target = dict((proposal.payload_json or {}).get("target") or {})
        entity_type = target.get("target_type") or proposal.operation_type.removeprefix("create_").removeprefix("update_").removeprefix("delete_")
        entity_id = result.get("id") or result.get(f"{entity_type}_id") or change.get(f"{entity_type}_id") or target.get("target_id")
        canonical_name = result.get("name") or result.get("title") or change.get("name") or (change.get("setup_fields") or change.get("strategy_fields") or change.get("bot_fields") or {}).get("name")
        return {"operation_id": proposal.operation_type, "entity_type": entity_type, "entity_id": str(entity_id) if entity_id is not None else None, "canonical_name": canonical_name, "owner_user_id": proposal.user_id, "proposal_id": proposal.id, "execution_id": execution.id, "result_status": execution.status, "conversation_id": None, "run_id": proposal.run_id}
