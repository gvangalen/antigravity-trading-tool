import asyncio
import time
from types import SimpleNamespace

from sqlalchemy import delete, select

from backend.api import ai_assistant_api
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import (
    FinnV2Conversation,
    FinnV2OrchestratorResult,
    FinnV2ReasoningResult,
    FinnV2Run,
    FinnV2RunTrace,
    FinnV2StateSnapshot,
    FinnV2ValidationResult,
    FinnV2VerifiedResponse,
    FinnV2VerifierResult,
    User,
)
from backend.main import app
from backend.schemas.assistant_schema import AssistantChatRequest
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services import finn_v2_reasoning_service as reasoning_module
from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService


class _FakeValidationRepo:
    def __init__(self):
        self.rows = {}

    async def get_for_snapshot_version(self, **kwargs):
        return self.rows.get(
            (
                kwargs["snapshot_id"],
                kwargs["user_id"],
                kwargs["validator_version"],
            )
        )

    async def create(self, **kwargs):
        self.rows[(kwargs["snapshot_id"], kwargs["user_id"], kwargs["validator_version"])] = SimpleNamespace(**kwargs)


class _StubFinnPlanService:
    async def hydrate_context(self, user_id, context):
        return dict(context or {})

    def sanitize_context_for_query(self, query, context):
        return dict(context or {})


class _Selection:
    selected_runtime = "v2"
    visible_allowed = True
    fallback_allowed = False
    runtime_mode = "v2_only"
    interaction_mode = "UNAVAILABLE"

    def dict(self):
        return {
            "runtime_mode": self.runtime_mode,
            "selected_runtime": self.selected_runtime,
            "interaction_mode": self.interaction_mode,
            "visible_allowed": self.visible_allowed,
            "shadow_enabled": False,
            "fallback_allowed": self.fallback_allowed,
            "reason_codes": [],
        }


class _Selector:
    def select(self, **kwargs):
        return _Selection()


async def _cleanup_user_rows(user_id: int) -> None:
    async with async_session_factory() as session:
        for model in [
            FinnV2VerifiedResponse,
            FinnV2VerifierResult,
            FinnV2ReasoningResult,
            FinnV2OrchestratorResult,
            FinnV2ValidationResult,
            FinnV2StateSnapshot,
            FinnV2RunTrace,
            FinnV2Run,
            FinnV2Conversation,
        ]:
            await session.execute(delete(model).where(model.user_id == user_id))
        await session.execute(delete(User).where(User.id == user_id))
        await session.commit()


async def _create_user(email: str) -> int:
    async with async_session_factory() as session:
        user = User(
            email=email,
            password_hash="not-used-in-test",
            role="user",
            is_active=True,
            first_name="Smoke",
            ai_preferences={"locale": "nl"},
        )
        session.add(user)
        await session.commit()
        return int(user.id)


async def _fetch_run_bundle(user_id: int):
    async with async_session_factory() as session:
        run = (
            await session.execute(select(FinnV2Run).where(FinnV2Run.user_id == user_id).order_by(FinnV2Run.created_at.desc()))
        ).scalars().first()
        conversation = (
            await session.execute(select(FinnV2Conversation).where(FinnV2Conversation.user_id == user_id).order_by(FinnV2Conversation.created_at.desc()))
        ).scalars().first()
        verified = (
            await session.execute(select(FinnV2VerifiedResponse).where(FinnV2VerifiedResponse.user_id == user_id).order_by(FinnV2VerifiedResponse.created_at.desc()))
        ).scalars().first()
        validation = (
            await session.execute(select(FinnV2ValidationResult).where(FinnV2ValidationResult.user_id == user_id).order_by(FinnV2ValidationResult.validated_at.desc()))
        ).scalars().first()
        traces = (
            await session.execute(select(FinnV2RunTrace).where(FinnV2RunTrace.user_id == user_id).order_by(FinnV2RunTrace.event_order.asc()))
        ).scalars().all()
        return run, conversation, verified, validation, traces


def test_evidence_validator_handles_empty_snapshot_without_none_payload_crash():
    service = FinnV2EvidenceValidatorService(session=object())
    service.validations = _FakeValidationRepo()
    service.redaction = SimpleNamespace(payload_to_jsonable=lambda value: value.dict())

    snapshot = FinancialStateSnapshot.parse_obj(
        {
            "snapshot_id": "snap-empty",
            "run_id": "run-empty",
            "user_id": 351,
            "revision": 1,
            "evidence_set_hash": "hash-empty",
            "nodes": [],
            "edges": [],
            "tool_outcomes": [],
            "assembled_at": "2026-08-18T00:00:00Z",
        }
    )

    validation = asyncio.run(service.validate_snapshot(snapshot))

    assert validation.validation_id.startswith("finn-v2-validation-")
    assert validation.integrity_status == "valid"
    assert all(domain.status == "not_collected" for domain in validation.domains)


def test_assistant_chat_v2_only_new_user_persists_run_and_verified_response(monkeypatch):
    email = f"codex-v2-route-{int(time.time() * 1000)}@example.net"

    async def _identity_context(db, user_id, payload=None, *, query=None):
        payload = dict(payload or {})
        payload.update(
            {
                "locale": "nl",
                "user_id": user_id,
                "symbol": None,
                "asset": None,
                "surface": "assistant_visible_v2",
                "missing_context": ["asset", "setup", "scores", "latest_report"],
                "trader_profile_used": False,
                "trader_profile": {
                    "asset_focus": [],
                    "trader_types": [],
                    "risk_profiles": [],
                    "behavior_flags": [],
                    "investment_goals": [],
                    "experience_levels": [],
                    "primary_timeframes": [],
                },
            }
        )
        return payload

    async def _graph_context(*, db, user_id, query, context_payload=None):
        return await _identity_context(db, user_id, context_payload, query=query)

    async def _exercise_route() -> tuple[dict, int, object, object, object, object, list]:
        user_id = await _create_user(email)
        try:
            async with async_session_factory() as session:
                response = await ai_assistant_api.assistant_chat(
                    request=AssistantChatRequest(
                        query="Hoi FINN, wat kun je voor mij doen?",
                        context={},
                        history=[],
                        session_id=None,
                    ),
                    raw_request=SimpleNamespace(
                        scope={"path": "/api/assistant/chat"},
                        state=SimpleNamespace(trace_id="trace-new-user-v2"),
                        headers={},
                        client=SimpleNamespace(host="127.0.0.1"),
                    ),
                    x_trace_id="trace-new-user-v2",
                    current_user={"id": user_id, "email": email, "role": "user"},
                    service=object(),
                    db=session,
                )
                await session.commit()
                payload = response.dict()

            run, conversation, verified, validation, traces = await _fetch_run_bundle(user_id)
            return payload, user_id, run, conversation, verified, validation, traces
        finally:
            await _cleanup_user_rows(user_id)

    try:
        monkeypatch.setattr(ai_assistant_api, "_new_finn_plan_service", lambda db, trace_id=None: _StubFinnPlanService())
        monkeypatch.setattr(ai_assistant_api, "_enrich_with_trader_profile", _identity_context)
        monkeypatch.setattr(ai_assistant_api, "_apply_canonical_finn_context_graph", _graph_context)
        monkeypatch.setattr(ai_assistant_api, "FinnV2RuntimeSelectorService", _Selector)
        monkeypatch.setattr(reasoning_module.openai_client, "get_openai_runtime_status", lambda: {"configured": False, "model": "test-disabled"})
        monkeypatch.setattr(reasoning_module.openai_client, "get_ai_availability", lambda: {"available": False, "reason": "ai_unavailable_configuration"})
        monkeypatch.setenv("FINN_V2_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_WRITE_BLOCKED", "1")
        monkeypatch.setenv("FINN_V2_MAX_EXECUTES_PER_MINUTE", "0")
        monkeypatch.setenv("FINN_V2_ALLOWED_TRANSPORTS", "chat,stream")
        monkeypatch.setenv("FINN_V2_RUNTIME_MODE", "v2_only")
        monkeypatch.setenv("FINN_V2_TOOL_REGISTRY_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_STATE_ASSEMBLY_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_POLICY_ENGINE_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_REASONING_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_RESPONSE_VERIFIER_ENABLED", "1")
        monkeypatch.setenv("FINN_V2_RESPONSE_DELIVERY_ENABLED", "1")

        payload, _, run, conversation, verified, validation, traces = asyncio.run(_exercise_route())
        assert payload["flow"] != "finn_v2_visible_failed"
        assert payload["response_trace"]["run_id"]
        assert payload["response"]
        assert conversation is not None
        assert run is not None
        assert run.status == "completed"
        assert run.id == payload["response_trace"]["run_id"]
        assert validation is not None
        assert verified is not None
        assert payload["flow"] == "finn_v2_visible"
        assert "evidence_validation_failed" not in [trace.event_type for trace in traces]
        assert "evidence_validation_completed" in [trace.event_type for trace in traces]
    finally:
        app.dependency_overrides.clear()
