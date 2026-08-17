import asyncio
from datetime import datetime, timezone
from starlette.requests import Request
from pydantic import SecretStr

from backend.api.ai_assistant_api import assistant_v2_confirm_proposal
from backend.schemas.finn_v2_execution_schema import FinnV2ExecuteProposalRequest


def _request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 12345)})


def test_confirmation_route_returns_confirmation_payload(monkeypatch):
    monkeypatch.setattr("backend.api.ai_assistant_api.execute_rate_limiter.check_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr("backend.services.finn_v2_flag_service.FinnV2FlagService.is_confirmation_routes_enabled", lambda self: True)

    class ConfirmationService:
        async def confirm(self, **kwargs):
            return type(
                "Result",
                (),
                {
                    "dict": lambda self: {
                        "confirmation_id": "confirm-1",
                        "proposal_id": "proposal-1",
                        "confirmed": True,
                        "already_confirmed": False,
                        "step_up_required": False,
                        "step_up_satisfied": False,
                        "eligibility_must_be_rechecked": True,
                        "reasons": [],
                        "created_at": datetime.now(timezone.utc),
                    }
                },
            )()

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ConfirmationService", lambda db: ConfirmationService())

    result = asyncio.run(
        assistant_v2_confirm_proposal(
            "proposal-1",
            FinnV2ExecuteProposalRequest(
                idempotency_key="abcdefgh",
                confirmation_token=SecretStr("token-1"),
                expected_payload_hash="hash-1",
            ),
            _request(),
            None,
            {"id": 7},
            object(),
        )
    )

    assert result["confirmed"] is True
    assert result["proposal_id"] == "proposal-1"
