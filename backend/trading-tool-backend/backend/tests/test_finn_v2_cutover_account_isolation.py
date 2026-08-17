import asyncio

import pytest
from fastapi import HTTPException

from backend.api.ai_assistant_api import assistant_v2_get_proposal


def test_proposal_lookup_is_account_scoped(monkeypatch):
    class ProposalRepo:
        async def get_by_id_for_user(self, **kwargs):
            return None

    monkeypatch.setattr("backend.infrastructure.repositories.finn_v2_proposal_repository.FinnV2ProposalRepository", lambda db: ProposalRepo())

    with pytest.raises(HTTPException) as exc:
        asyncio.run(assistant_v2_get_proposal("proposal-foreign", {"id": 9}, object()))

    assert exc.value.status_code == 404
