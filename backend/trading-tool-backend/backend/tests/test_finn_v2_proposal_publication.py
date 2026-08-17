import asyncio
from datetime import datetime, timedelta, timezone
from starlette.requests import Request

from backend.api.ai_assistant_api import assistant_v2_publish_proposal


def _request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})


def test_proposal_publication_returns_pending_confirmation(monkeypatch):
    monkeypatch.setattr("backend.api.ai_assistant_api.execute_rate_limiter.check_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.services.finn_v2_flag_service.FinnV2FlagService.is_visible_proposals_enabled", lambda self: True)
    monkeypatch.setattr("backend.services.finn_v2_flag_service.FinnV2FlagService.is_confirmation_routes_enabled", lambda self: True)

    class ConfirmationService:
        async def issue_confirmation_token(self, **kwargs):
            return "token-1", datetime.now(timezone.utc) + timedelta(minutes=5)

    class ProposalRepo:
        async def get_by_id_for_user(self, **kwargs):
            return type("Proposal", (), {"payload_hash": "hash-1"})()

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ConfirmationService", lambda db: ConfirmationService())
    monkeypatch.setattr("backend.infrastructure.repositories.finn_v2_proposal_repository.FinnV2ProposalRepository", lambda db: ProposalRepo())

    result = asyncio.run(
        assistant_v2_publish_proposal(
            "proposal-1",
            _request(),
            None,
            {"id": 7},
            object(),
        )
    )

    assert result["status"] == "pending_confirmation"
    assert result["payload_hash"] == "hash-1"
