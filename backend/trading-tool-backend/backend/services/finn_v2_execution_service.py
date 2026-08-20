from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_execution_repository import FinnV2ExecutionRepository
from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
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
            postcondition_hash = await self.adapters.postcondition_hash(proposal.operation_type, user_id=user_id, payload=result_payload)
            execution.status = "succeeded"
            execution.postcondition_hash = postcondition_hash
            execution.result_json = result_payload
            execution.completed_at = datetime.now(timezone.utc)
            await self.session.flush()
            record_latency_sample(f"finn_v2_execution_latency_ms:{proposal.operation_type}", int((execution.completed_at - started_at).total_seconds() * 1000))
            increment_execution_safety_counter(f"finn_v2_executions_total:{proposal.operation_type}:succeeded")
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

    def _hash(self, payload: dict) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
