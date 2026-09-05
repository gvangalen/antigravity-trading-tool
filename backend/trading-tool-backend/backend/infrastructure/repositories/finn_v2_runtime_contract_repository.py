from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.finn_v2_runtime_contract import (
    RUNTIME_CONTRACT_VERSION,
    RuntimeContractConflictError,
    new_runtime_contract_state,
    record_initial_intent,
    record_conversation_state,
    record_selection,
    terminal_projection,
)
from backend.infrastructure.models import FinnV2RuntimeContract
from backend.infrastructure.repositories.finn_v2_repository_transaction_mixin import FinnV2RepositoryTransactionMixin


class FinnV2RuntimeContractRepository(FinnV2RepositoryTransactionMixin):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_for_run(self, *, run) -> FinnV2RuntimeContract:
        existing = await self.get_for_run(run_id=run.id, for_update=True)
        if existing is not None:
            return existing
        contract_id = f"finn-v2-contract-{run.id}"
        row = FinnV2RuntimeContract(
            contract_id=contract_id,
            run_id=run.id,
            conversation_id=run.conversation_id,
            trace_id=run.trace_id,
            user_id=run.user_id,
            contract_version=RUNTIME_CONTRACT_VERSION,
            revision=0,
            state_json=new_runtime_contract_state(run=run, contract_id=contract_id),
        )
        self.session.add(row)
        await self._flush_with_rollback(operation="create_runtime_contract", entity_type="FinnV2RuntimeContract", run_id=run.id)
        return row

    async def get_for_run(self, *, run_id: str, for_update: bool = False) -> Optional[FinnV2RuntimeContract]:
        statement = select(FinnV2RuntimeContract).where(FinnV2RuntimeContract.run_id == run_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def get_latest_for_conversation(
        self, *, conversation_id: str, user_id: int
    ) -> Optional[FinnV2RuntimeContract]:
        result = await self.session.execute(
            select(FinnV2RuntimeContract)
            .where(
                FinnV2RuntimeContract.conversation_id == conversation_id,
                FinnV2RuntimeContract.user_id == user_id,
            )
            .order_by(desc(FinnV2RuntimeContract.updated_at))
            .limit(1)
        )
        return result.scalars().first()

    @staticmethod
    def execution_view(row: FinnV2RuntimeContract) -> Dict[str, Any]:
        """Return the authoritative execution fields for a new contract run.

        Orchestration artifacts retain tool/evidence detail, but consumers must
        take operation, mode, target and lineage identity from this view.
        """
        state = dict(row.state_json or {})
        return {
            "contract_id": row.contract_id,
            "contract_revision": int(row.revision or 0),
            "initial_operation_id": state.get("initial_operation_id"),
            "operation_id": state.get("final_operation_id") or state.get("initial_operation_id"),
            "interaction_mode": state.get("final_mode") or state.get("requested_mode"),
            "target_asset": state.get("canonical_target"),
            "target_asset_source": state.get("target_source"),
            "referenced_asset": state.get("original_target_text"),
            "conversation_reference": state.get("conversation_reference"),
            "conversation_reference_kind": state.get("conversation_reference_kind"),
            "selector_provenance": dict(state.get("selector_provenance") or {}),
        }

    async def record_initial_intent(self, *, run_id: str, operation_id: str, requested_mode: str) -> FinnV2RuntimeContract:
        row = await self._required_for_update(run_id)
        current_state = row.state_json or {}
        if current_state.get("initial_operation_id") is not None:
            # Retries may observe the same immutable selector decision, but they
            # must not create another state transition or revision.
            record_initial_intent(current_state, operation_id=operation_id, requested_mode=requested_mode)
            return row
        next_state = record_initial_intent(current_state, operation_id=operation_id, requested_mode=requested_mode)
        return await self._write_revision(row=row, state=next_state)

    async def record_selection(
        self,
        *,
        run_id: str,
        canonical_target: Optional[str],
        target_source: Optional[str],
        original_target_text: Optional[str],
        target_type: Optional[str],
        conversation_reference: Optional[str],
        conversation_reference_kind: Optional[str],
        selector_provenance: Optional[Dict[str, Any]] = None,
    ) -> FinnV2RuntimeContract:
        """Persist the target selection before tool planning or policy reads it."""
        row = await self._required_for_update(run_id)
        next_state = record_selection(
            deepcopy(row.state_json or {}),
            canonical_target=canonical_target,
            target_source=target_source,
            original_target_text=original_target_text,
            target_type=target_type,
            conversation_reference=conversation_reference,
            conversation_reference_kind=conversation_reference_kind,
            selector_provenance=selector_provenance,
        )
        if next_state == (row.state_json or {}):
            return row
        return await self._write_revision(row=row, state=next_state)

    async def record_conversation_state(
        self, *, run_id: str, lineage_state: Dict[str, Any], guided_state: Dict[str, Any]
    ) -> FinnV2RuntimeContract:
        row = await self._required_for_update(run_id)
        next_state = record_conversation_state(
            deepcopy(row.state_json or {}),
            lineage_state=lineage_state,
            guided_state=guided_state,
        )
        return await self._write_revision(row=row, state=next_state)

    async def materialize_terminal(
        self,
        *,
        run_id: str,
        status: str,
        mode: Optional[str],
        response: Optional[Dict[str, Any]],
        error_code: Optional[str] = None,
    ) -> FinnV2RuntimeContract:
        row = await self._required_for_update(run_id)
        state = deepcopy(row.state_json or {})
        state["final_operation_id"] = state.get("final_operation_id") or state.get("initial_operation_id")
        state["final_mode"] = mode or state.get("final_mode") or state.get("requested_mode")
        state["terminal_status"] = status
        state["terminal_response_type"] = "failure" if status == "failed" else "response"
        timestamps = dict(state.get("phase_timestamps") or {})
        timestamps.setdefault("created_at", row.created_at.astimezone(timezone.utc).isoformat())
        timestamps["terminal_at"] = datetime.now(timezone.utc).isoformat()
        state["phase_timestamps"] = timestamps
        state.setdefault("transition_log", []).append({"type": "terminal", "status": status})
        projection = terminal_projection(state, status=status, mode=mode, response=response, error_code=error_code)
        row = await self._write_revision(row=row, state=state)
        row.terminal_projection_json = projection
        await self._flush_with_rollback(operation="materialize_runtime_terminal", entity_type="FinnV2RuntimeContract", run_id=run_id)
        return row

    async def record_lifecycle_status(self, *, run_id: str, status: str, mode: Optional[str]) -> FinnV2RuntimeContract:
        row = await self._required_for_update(run_id)
        state = deepcopy(row.state_json or {})
        state["current_status"] = status
        timestamps = dict(state.get("phase_timestamps") or {})
        timestamps.setdefault("created_at", row.created_at.astimezone(timezone.utc).isoformat())
        timestamps.setdefault(status, datetime.now(timezone.utc).isoformat())
        state["phase_timestamps"] = timestamps
        if mode:
            state["current_mode"] = mode
        state.setdefault("transition_log", []).append({"type": "lifecycle", "status": status})
        return await self._write_revision(row=row, state=state)

    async def _required_for_update(self, run_id: str) -> FinnV2RuntimeContract:
        row = await self.get_for_run(run_id=run_id, for_update=True)
        if row is None:
            raise LookupError("finn_v2_runtime_contract_missing")
        return row

    async def _write_revision(self, *, row: FinnV2RuntimeContract, state: Dict[str, Any]) -> FinnV2RuntimeContract:
        identity = state.get("identity") or {}
        expected_identity = {
            "run_id": row.run_id,
            "conversation_id": row.conversation_id,
            "trace_id": row.trace_id,
            "user_id": row.user_id,
        }
        if identity != expected_identity or state.get("contract_id") != row.contract_id or state.get("contract_version") != row.contract_version:
            raise RuntimeContractConflictError("runtime_contract_identity_is_immutable")
        row.state_json = state
        row.revision = int(row.revision or 0) + 1
        row.updated_at = datetime.now(timezone.utc)
        await self._flush_with_rollback(operation="update_runtime_contract", entity_type="FinnV2RuntimeContract", run_id=row.run_id)
        return row
