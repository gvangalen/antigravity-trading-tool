from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService


def test_confirmation_accepts_valid_token_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")
    service = FinnV2ConfirmationService(session=object())
    service.flags.is_confirmations_enabled = lambda: True
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        payload_hash="payload-hash",
        status="pending_confirmation",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.proposals.update_status = lambda *_args, **_kwargs: asyncio.sleep(0, result=proposal)

    raw_token = "token-1"
    token_hash = service._token_hash(
        proposal_id="proposal-1",
        user_id=7,
        payload_hash="payload-hash",
        expires_at=proposal.expires_at,
        raw_token=raw_token,
    )
    confirmation = SimpleNamespace(
        id="confirmation-1",
        proposal_id="proposal-1",
        user_id=7,
        token_hash=token_hash,
        payload_hash="payload-hash",
        confirmed=False,
        already_confirmed=False,
        created_at=datetime.now(timezone.utc),
    )
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=confirmation)
    service.confirmations.update = lambda row, **kwargs: asyncio.sleep(0, result=SimpleNamespace(**{**row.__dict__, **kwargs}))

    request = FinnV2ConfirmationRequest(proposal_id="proposal-1", confirmation_token=raw_token, expected_payload_hash="payload-hash")
    first = asyncio.run(service.confirm(user_id=7, request=request))
    confirmation.confirmed = True
    second = asyncio.run(service.confirm(user_id=7, request=request))

    assert first.confirmed is True
    assert second.already_confirmed is True
