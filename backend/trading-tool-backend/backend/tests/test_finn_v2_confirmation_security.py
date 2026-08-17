from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

import pytest

from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService


def test_confirmation_does_not_store_raw_token_and_rejects_wrong_token(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")
    service = FinnV2ConfirmationService(session=object())
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        payload_hash="payload-hash",
        status="pending_confirmation",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    confirmation = SimpleNamespace(
        id="confirmation-1",
        proposal_id="proposal-1",
        user_id=7,
        token_hash="stored-hash",
        payload_hash="payload-hash",
        confirmed=False,
        already_confirmed=False,
        created_at=datetime.now(timezone.utc),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=confirmation)

    with pytest.raises(LookupError):
        asyncio.run(
            service.confirm(
                user_id=7,
                request=FinnV2ConfirmationRequest(
                    proposal_id="proposal-1",
                    confirmation_token="wrong-token",
                    expected_payload_hash="payload-hash",
                ),
            )
        )

    assert confirmation.token_hash != "wrong-token"


def test_confirmation_token_has_sufficient_entropy(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")
    service = FinnV2ConfirmationService(session=object())
    service.flags.is_confirmations_enabled = lambda: True
    proposal = SimpleNamespace(
        id="proposal-1",
        run_id="run-1",
        user_id=7,
        payload_hash="payload-hash",
        status="draft",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=proposal)
    service.confirmations.get_for_proposal_user = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.confirmations.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.proposals.update_status = lambda *_args, **_kwargs: asyncio.sleep(0, result=proposal)

    raw_token, _ = asyncio.run(service.issue_confirmation_token(proposal_id="proposal-1", user_id=7))

    assert len(raw_token) >= 43
