from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import asyncio

import pytest

from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService


def test_confirmation_replay_with_wrong_user_leaks_nothing(monkeypatch):
    monkeypatch.setenv("FINN_V2_CONFIRMATION_SECRET", "secret")
    service = FinnV2ConfirmationService(session=object())
    service.proposals.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=None)

    with pytest.raises(LookupError):
        asyncio.run(
            service.confirm(
                user_id=99,
                request=FinnV2ConfirmationRequest(
                    proposal_id="proposal-1",
                    confirmation_token="token",
                    expected_payload_hash="payload-hash",
                ),
            )
        )
