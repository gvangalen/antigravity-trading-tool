from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_confirmation_repository import FinnV2ConfirmationRepository
from backend.infrastructure.repositories.finn_v2_eligibility_repository import FinnV2EligibilityRepository
from backend.infrastructure.repositories.finn_v2_policy_repository import FinnV2PolicyRepository
from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
from backend.infrastructure.repositories.finn_v2_state_repository import FinnV2StateRepository
from backend.infrastructure.repositories.finn_v2_validation_repository import FinnV2ValidationRepository
from backend.schemas.finn_v2_policy_schema import ELIGIBILITY_VERSION, ExecutionEligibilityDecision, StepUpProof
from backend.services.finn_v2_flag_service import FinnV2FlagService


class FinnV2ExecutionGateService:
    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.proposals = FinnV2ProposalRepository(session)
        self.confirmations = FinnV2ConfirmationRepository(session)
        self.policies = FinnV2PolicyRepository(session)
        self.states = FinnV2StateRepository(session)
        self.validations = FinnV2ValidationRepository(session)
        self.eligibility = FinnV2EligibilityRepository(session)

    async def check_execution_eligibility(
        self,
        *,
        user_id: int,
        run_id: str,
        proposal_id: str,
        step_up_proof: StepUpProof | None = None,
    ) -> ExecutionEligibilityDecision:
        proposal = await self.proposals.get_by_id_for_user(proposal_id=proposal_id, user_id=user_id)
        if proposal is None or proposal.run_id != run_id:
            raise LookupError("proposal_not_owned")
        policy = await self.policies.get_by_id_for_user(policy_decision_id=proposal.policy_decision_id, user_id=user_id)
        if policy is None:
            raise LookupError("proposal_not_owned")
        confirmation = await self.confirmations.get_for_proposal_user(proposal_id=proposal.id, user_id=user_id)
        snapshot = await self.states.get_by_evidence_hash(run_id=run_id, user_id=user_id, evidence_set_hash=proposal.evidence_set_hash)
        validation = None
        if snapshot is not None:
            validation = await self.validations.get_for_snapshot_version(
                snapshot_id=snapshot.id,
                user_id=user_id,
                validator_version="2026-08-17.block3",
            )

        proposal_confirmed = bool(confirmation and confirmation.confirmed and proposal.status == "confirmed")
        payload_hash_valid = self._payload_hash(proposal.payload_json) == proposal.payload_hash
        evidence_hash_valid = bool(snapshot and validation and snapshot.evidence_set_hash == proposal.evidence_set_hash and validation.evidence_set_hash == proposal.evidence_set_hash)
        freshness_valid = True
        kill_switch_clear = not self.flags.is_action_kill_switch_enabled()
        feature_enabled = self.flags.is_execution_gate_enabled()
        duplicate_execution_clear = True
        step_up_required = bool(proposal.requires_step_up_auth)
        step_up_satisfied = bool(step_up_proof and step_up_proof.user_id == user_id and step_up_proof.expires_at > datetime.now(timezone.utc))
        blocking_codes: list[str] = []

        if not proposal_confirmed:
            blocking_codes.append("proposal_not_confirmed")
        if proposal.expires_at <= datetime.now(timezone.utc):
            blocking_codes.append("proposal_expired")
        if not payload_hash_valid:
            blocking_codes.append("proposal_payload_hash_mismatch")
        if not evidence_hash_valid:
            blocking_codes.append("proposal_evidence_hash_mismatch")
        if step_up_required and not step_up_satisfied:
            blocking_codes.append("step_up_required")
        if not kill_switch_clear:
            blocking_codes.append("kill_switch_enabled")
        if not feature_enabled:
            blocking_codes.append("feature_disabled")
        if proposal.operation_type == "activate_live_bot" and not self.flags.is_live_actions_enabled():
            blocking_codes.append("live_action_disabled")
        if proposal.operation_type in {"manual_order", "portfolio_rebalance"}:
            blocking_codes.append("shadow_mode_execution_blocked")
        if proposal.operation_type == "activate_live_bot":
            freshness_valid = False
            blocking_codes.append("shadow_mode_execution_blocked")
        eligible = False

        decision = ExecutionEligibilityDecision(
            eligibility_id=f"finn-v2-eligibility-{uuid.uuid4().hex}",
            proposal_id=proposal.id,
            run_id=run_id,
            user_id=user_id,
            eligible=eligible,
            policy_class=policy.policy_class,
            proposal_confirmed=proposal_confirmed,
            payload_hash_valid=payload_hash_valid,
            evidence_hash_valid=evidence_hash_valid,
            freshness_valid=freshness_valid,
            step_up_required=step_up_required,
            step_up_satisfied=step_up_satisfied,
            kill_switch_clear=kill_switch_clear,
            feature_enabled=feature_enabled,
            duplicate_execution_clear=duplicate_execution_clear,
            blocking_codes=blocking_codes,
            eligibility_version=ELIGIBILITY_VERSION,
            checked_at=datetime.now(timezone.utc),
        )
        await self.eligibility.create(
            id=decision.eligibility_id,
            proposal_id=proposal.id,
            run_id=run_id,
            user_id=user_id,
            eligible=decision.eligible,
            policy_class=decision.policy_class,
            decision_json=decision.dict(),
            eligibility_version=decision.eligibility_version,
            checked_at=decision.checked_at,
        )
        return decision

    def _payload_hash(self, payload_json: dict) -> str:
        canonical = json.dumps(payload_json, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
