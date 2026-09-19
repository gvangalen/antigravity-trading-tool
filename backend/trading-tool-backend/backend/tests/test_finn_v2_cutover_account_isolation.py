import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

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


def test_proposal_summary_exposes_only_immutable_update_review_state(monkeypatch):
    now = datetime.now(timezone.utc)
    proposal = SimpleNamespace(
        id="proposal-owned",
        run_id="run-owned",
        user_id=9,
        status="draft",
        operation_type="update_setup",
        target_type="setup",
        target_id="12",
        asset="BTC",
        payload_hash="payload-hash",
        evidence_set_hash="evidence-hash",
        requires_step_up_auth=False,
        expires_at=now + timedelta(minutes=5),
        payload_json={
            "change": {
                "setup_id": 12,
                "before_state": {"timeframe": "1W"},
                "requested_state": {"timeframe": "1D"},
                "target_revision": "revision-hash",
                "snapshot_timestamp": now.isoformat(),
                "internal_adapter_detail": "not-public",
            },
        },
    )

    class ProposalRepo:
        async def get_by_id_for_user(self, **kwargs):
            assert kwargs == {"proposal_id": "proposal-owned", "user_id": 9}
            return proposal

    monkeypatch.setattr("backend.infrastructure.repositories.finn_v2_proposal_repository.FinnV2ProposalRepository", lambda db: ProposalRepo())

    result = asyncio.run(assistant_v2_get_proposal("proposal-owned", {"id": 9}, object()))

    assert result.before_state == {"timeframe": "1W"}
    assert result.requested_state == {"timeframe": "1D"}
    assert result.target_revision == "revision-hash"
    assert result.snapshot_timestamp == now
    assert not hasattr(result, "internal_adapter_detail")
