from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.repositories.finn_v2_confirmation_repository import FinnV2ConfirmationRepository
from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest, FinnV2ConfirmationResult
from backend.services.finn_v2_flag_service import FinnV2FlagService


class FinnV2ConfirmationService:
    def __init__(self, session: AsyncSession, flag_service: Optional[FinnV2FlagService] = None):
        self.session = session
        self.flags = flag_service or FinnV2FlagService()
        self.confirmations = FinnV2ConfirmationRepository(session)
        self.proposals = FinnV2ProposalRepository(session)

    async def issue_confirmation_token(self, *, proposal_id: str, user_id: int) -> tuple[str, datetime]:
        if not self.flags.is_confirmations_enabled():
            raise ValueError("feature_disabled")
        proposal = await self.proposals.get_by_id_for_user(proposal_id=proposal_id, user_id=user_id)
        if proposal is None:
            raise LookupError("proposal_not_owned")
        raw_token = secrets.token_urlsafe(48)
        expires_at = min(
            proposal.expires_at,
            datetime.now(timezone.utc) + timedelta(seconds=self.flags.proposal_ttl_seconds()),
        )
        token_hash = self._token_hash(
            proposal_id=proposal.id,
            user_id=user_id,
            payload_hash=proposal.payload_hash,
            expires_at=expires_at,
            raw_token=raw_token,
        )
        existing = await self.confirmations.get_for_proposal_user(proposal_id=proposal.id, user_id=user_id)
        if existing is None:
            await self.confirmations.create(
                id=f"finn-v2-confirmation-{uuid.uuid4().hex}",
                proposal_id=proposal.id,
                run_id=proposal.run_id,
                user_id=user_id,
                token_hash=token_hash,
                payload_hash=proposal.payload_hash,
                confirmed=False,
                already_confirmed=False,
            )
        else:
            await self.confirmations.update(existing, token_hash=token_hash, payload_hash=proposal.payload_hash, confirmed=False, already_confirmed=False)
        await self.proposals.update_status(proposal, status="pending_confirmation")
        return raw_token, expires_at

    async def confirm(
        self,
        *,
        user_id: int,
        request: FinnV2ConfirmationRequest,
        step_up_required: bool = False,
        step_up_satisfied: bool = False,
    ) -> FinnV2ConfirmationResult:
        proposal = await self.proposals.get_by_id_for_user(proposal_id=request.proposal_id, user_id=user_id)
        if proposal is None:
            raise LookupError("confirmation_token_invalid")
        confirmation = await self.confirmations.get_for_proposal_user(proposal_id=proposal.id, user_id=user_id)
        if confirmation is None:
            raise LookupError("confirmation_token_invalid")
        if proposal.expires_at <= datetime.now(timezone.utc):
            raise ValueError("confirmation_token_expired")
        if request.expected_payload_hash != proposal.payload_hash or request.expected_payload_hash != confirmation.payload_hash:
            raise ValueError("proposal_payload_hash_mismatch")

        candidate_hash = self._token_hash(
            proposal_id=proposal.id,
            user_id=user_id,
            payload_hash=proposal.payload_hash,
            expires_at=proposal.expires_at,
            raw_token=request.confirmation_token.get_secret_value(),
        )
        if not hmac.compare_digest(candidate_hash, confirmation.token_hash):
            raise LookupError("confirmation_token_invalid")

        if confirmation.confirmed:
            return FinnV2ConfirmationResult(
                confirmation_id=confirmation.id,
                proposal_id=proposal.id,
                confirmed=True,
                already_confirmed=True,
                step_up_required=step_up_required,
                step_up_satisfied=step_up_satisfied,
                eligibility_must_be_rechecked=True,
                reasons=[],
                created_at=confirmation.created_at,
            )

        await self.confirmations.update(confirmation, confirmed=True, already_confirmed=False)
        await self.proposals.update_status(proposal, status="confirmed")
        return FinnV2ConfirmationResult(
            confirmation_id=confirmation.id,
            proposal_id=proposal.id,
            confirmed=True,
            already_confirmed=False,
            step_up_required=step_up_required,
            step_up_satisfied=step_up_satisfied,
            eligibility_must_be_rechecked=True,
            reasons=[],
            created_at=confirmation.created_at,
        )

    def _token_hash(self, *, proposal_id: str, user_id: int, payload_hash: str, expires_at: datetime, raw_token: str) -> str:
        secret = os.getenv("FINN_V2_CONFIRMATION_SECRET")
        if not secret:
            raise ValueError("feature_disabled")
        message = "|".join([proposal_id, str(user_id), payload_hash, expires_at.isoformat(), raw_token]).encode("utf-8")
        return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
