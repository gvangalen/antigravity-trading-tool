import asyncio
from datetime import datetime, timezone
from starlette.requests import Request
from pydantic import SecretStr

from backend.api.ai_assistant_api import assistant_v2_confirm_proposal, assistant_v2_execute_proposal
from backend.api import ai_assistant_api
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


def test_execution_replay_does_not_consume_a_second_mutation_rate_slot(monkeypatch):
    calls = []
    invalidated_users = []
    monkeypatch.setattr(
        "backend.api.ai_assistant_api.execute_rate_limiter.check_rate_limit",
        lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    monkeypatch.setattr("backend.services.finn_v2_flag_service.FinnV2FlagService.is_action_execution_enabled", lambda self: True)

    class ExecutionRepository:
        async def get_by_idempotency_key_for_user(self, **kwargs):
            return object()

    class ExecutionService:
        async def execute(self, **kwargs):
            return type("Result", (), {"dict": lambda self: {"status": "already_executed"}})()

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ExecutionRepository", lambda db: ExecutionRepository())
    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ExecutionService", lambda db: ExecutionService())
    monkeypatch.setattr(
        "backend.api.ai_assistant_api._invalidate_mission_control_cache",
        lambda user_id: invalidated_users.append(user_id),
    )
    monkeypatch.setattr(
        "backend.services.finn_plan_service.FinnPlanService.invalidate_runtime_caches_for_user",
        lambda user_id: invalidated_users.append(user_id),
    )

    result = asyncio.run(
        assistant_v2_execute_proposal(
            "proposal-1",
            FinnV2ExecuteProposalRequest(idempotency_key="abcdefgh", expected_payload_hash="hash-1"),
            _request(),
            None,
            {"id": 7},
            object(),
        )
    )

    assert result["status"] == "already_executed"
    assert calls == []
    assert invalidated_users == [7, 7]


def test_v2_execution_invalidates_the_cached_finn_today_projection(monkeypatch):
    monkeypatch.setattr(
        "backend.api.ai_assistant_api.execute_rate_limiter.check_rate_limit",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "backend.services.finn_v2_flag_service.FinnV2FlagService.is_action_execution_enabled",
        lambda self: True,
    )

    class ExecutionRepository:
        async def get_by_idempotency_key_for_user(self, **kwargs):
            return None

    class ExecutionService:
        async def execute(self, **kwargs):
            return type("Result", (), {"dict": lambda self: {"status": "succeeded"}})()

    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ExecutionRepository", lambda db: ExecutionRepository())
    monkeypatch.setattr("backend.api.ai_assistant_api.FinnV2ExecutionService", lambda db: ExecutionService())
    monkeypatch.setattr(
        "backend.services.finn_plan_service.FinnPlanService.invalidate_runtime_caches_for_user",
        lambda user_id: None,
    )
    ai_assistant_api._store_cached_mission_control(7, {"finn_briefing": {"summary": "€0,00"}})

    asyncio.run(
        assistant_v2_execute_proposal(
            "proposal-budget-update",
            FinnV2ExecuteProposalRequest(idempotency_key="budget-update-key", expected_payload_hash="hash-1"),
            _request(),
            None,
            {"id": 7},
            object(),
        )
    )

    assert ai_assistant_api._get_cached_mission_control(7) is None
