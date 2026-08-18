from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
from backend.infrastructure.repositories.finn_v2_run_repository import FinnV2RunRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.schemas.finn_v2_policy_schema import FinnV2PolicyDecision
from backend.schemas.finn_v2_proposal_schema import FinnV2ProposalRecord, ValidatedProposalInput
from backend.services.finn_v2_entity_resolution_service import FinnV2EntityResolutionService
from backend.services.finn_v2_flag_service import FinnV2FlagService
from backend.services.finn_v2_json_safety import to_json_safe


class FinnV2ProposalService:
    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.policies = FinnV2PolicyRepository(session)
        self.proposals = FinnV2ProposalRepository(session)
        self.runs = FinnV2RunRepository(session)
        self.states = FinnV2StateRepository(session)
        self.validations = FinnV2ValidationRepository(session)
        self.resolver = FinnV2EntityResolutionService(session)

    async def create_proposal(
        self,
        *,
        user_id: int,
        run_id: str,
        trace_id: str,
        policy: FinnV2PolicyDecision,
        proposal_input: ValidatedProposalInput,
    ) -> FinnV2ProposalRecord:
        if not self.flags.is_proposals_enabled():
            raise ValueError("feature_disabled")
        if policy.user_id != user_id or policy.run_id != run_id:
            raise LookupError("proposal_not_owned")
        if not policy.proposal_allowed:
            raise ValueError("proposal_not_allowed")
        if policy.operation_type and policy.operation_type != proposal_input.operation_type:
            raise ValueError("operation_policy_mismatch")
        if proposal_input.source_run_id != run_id:
            raise ValueError("operation_policy_mismatch")
        if proposal_input.expires_at <= datetime.now(timezone.utc):
            raise ValueError("proposal_expired")
        max_expiry = datetime.now(timezone.utc).timestamp() + self.flags.proposal_ttl_seconds()
        if proposal_input.expires_at.timestamp() > max_expiry:
            raise ValueError("proposal_expired")

        existing = await self.proposals.get_by_idempotency_key_for_user(
            idempotency_key=proposal_input.idempotency_key,
            user_id=user_id,
        )
        payload_json = to_json_safe(proposal_input.dict())
        payload_hash = self._payload_hash(payload_json)
        if existing is not None:
            if existing.payload_hash != payload_hash:
                raise ValueError("operation_payload_invalid")
            return self._row_to_record(existing)

        duplicate = await self.proposals.get_by_payload_hash_for_run(
            payload_hash=payload_hash,
            run_id=run_id,
            user_id=user_id,
        )
        if duplicate is not None:
            return self._row_to_record(duplicate)

        snapshot = await self.states.get_by_id_for_user(snapshot_id=proposal_input.source_snapshot_id, user_id=user_id)
        validation = await self.validations.get_by_id_for_user(validation_id=proposal_input.source_validation_id, user_id=user_id)
        if snapshot is None or validation is None:
            raise LookupError("proposal_not_owned")
        if snapshot.evidence_set_hash != proposal_input.evidence_set_hash or validation.evidence_set_hash != proposal_input.evidence_set_hash:
            raise ValueError("proposal_evidence_hash_mismatch")

        await self._validate_target_user_scope(user_id=user_id, proposal_input=proposal_input)

        row = await self.proposals.create(
            id=f"finn-v2-proposal-{uuid.uuid4().hex}",
            run_id=run_id,
            user_id=user_id,
            policy_decision_id=policy.policy_decision_id,
            status="draft",
            operation_type=proposal_input.operation_type,
            target_type=proposal_input.target.target_type,
            target_id=proposal_input.target.target_id,
            asset=proposal_input.target.asset,
            payload_json=payload_json,
            payload_hash=payload_hash,
            evidence_set_hash=proposal_input.evidence_set_hash,
            idempotency_key=proposal_input.idempotency_key,
            requires_step_up_auth=policy.step_up_required,
            expires_at=proposal_input.expires_at,
        )
        return self._row_to_record(row)

    async def _validate_target_user_scope(self, *, user_id: int, proposal_input: ValidatedProposalInput) -> None:
        target = proposal_input.target
        selector = {}
        if target.asset:
            selector["asset"] = target.asset
        if target.target_id and target.target_type == "setup":
            selector["setup_id"] = int(target.target_id)
            await self.resolver.resolve_setup(user_id=user_id, selector=selector, asset=target.asset)
        elif target.target_id and target.target_type == "strategy":
            selector["strategy_id"] = int(target.target_id)
            await self.resolver.resolve_strategy(user_id=user_id, selector=selector, setup=None)
        elif target.target_id and target.target_type == "bot":
            selector["bot_id"] = int(target.target_id)
            await self.resolver.resolve_bot(user_id=user_id, selector=selector, strategy=None)
        elif target.target_type == "indicator_configuration":
            await self.resolver.resolve_asset(user_id=user_id, selector=selector, workspace_hints={}, client_context={})
        elif target.target_type == "watchlist" and target.asset:
            await self.resolver.resolve_asset(user_id=user_id, selector=selector, workspace_hints={}, client_context={})
        elif target.target_type == "order" and target.asset:
            await self.resolver.resolve_asset(user_id=user_id, selector=selector, workspace_hints={}, client_context={})

    def _payload_hash(self, payload_json: dict) -> str:
        canonical = json.dumps(payload_json, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _row_to_record(self, row) -> FinnV2ProposalRecord:
        return FinnV2ProposalRecord(
            proposal_id=row.id,
            run_id=row.run_id,
            user_id=row.user_id,
            policy_decision_id=row.policy_decision_id,
            status=row.status,
            operation_type=row.operation_type,
            target={"target_type": row.target_type, "target_id": row.target_id, "asset": row.asset},
            payload_json=row.payload_json,
            payload_hash=row.payload_hash,
            evidence_set_hash=row.evidence_set_hash,
            idempotency_key=row.idempotency_key,
            requires_step_up_auth=row.requires_step_up_auth,
            created_at=row.created_at,
            updated_at=row.updated_at,
            expires_at=row.expires_at,
        )
