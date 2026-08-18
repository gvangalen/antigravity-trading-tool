from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

from backend.domain.finn_v2_contract import InvalidRunTransitionError, validate_run_transition
from backend.services.finn_v2_run_service import FinnV2RunService


ROOT = Path(__file__).resolve().parents[1]


class _NestedTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self, *, is_active=True):
        self.sync_session = SimpleNamespace(is_active=is_active)
        self.rollback_calls = 0
        self.commit_calls = 0

    def begin_nested(self):
        return _NestedTxn()

    def get_transaction(self):
        return SimpleNamespace(is_active=self.sync_session.is_active)

    async def commit(self):
        self.commit_calls += 1

    async def rollback(self):
        self.rollback_calls += 1
        self.sync_session.is_active = True


class _FakeRunRepo:
    def __init__(self, run):
        self.run = run

    async def get_by_id_for_user(self, *, run_id, user_id):
        if self.run.id == run_id and self.run.user_id == user_id:
            return self.run
        return None

    async def update_status(self, *, run, status, **kwargs):
        run.status = status
        for key, value in kwargs.items():
            if value is not None:
                setattr(run, key, value)
        return run

    async def create(self, **kwargs):
        return SimpleNamespace(**kwargs)

    async def _commit_with_rollback(self, **_kwargs):
        await self.session.commit()


class _FakeTraceRepo:
    def __init__(self):
        self.events = []

    async def append_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


class _FakeConversationRepo:
    def __init__(self):
        self.last_run = None

    async def set_last_run(self, *, conversation_id, user_id, run_id):
        self.last_run = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "run_id": run_id,
        }


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("created", "collecting"),
        ("created", "failed"),
        ("created", "canceled"),
        ("collecting", "planned"),
        ("collecting", "blocked"),
        ("collecting", "failed"),
        ("collecting", "canceled"),
        ("planned", "completed"),
        ("planned", "blocked"),
        ("planned", "failed"),
        ("planned", "canceled"),
    ],
)
def test_allowed_run_transitions(current_status, next_status):
    validate_run_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("created", "completed"),
        ("collecting", "completed"),
        ("blocked", "completed"),
        ("completed", "failed"),
        ("failed", "planned"),
        ("canceled", "collecting"),
    ],
)
def test_forbidden_run_transitions(current_status, next_status):
    with pytest.raises(InvalidRunTransitionError):
        validate_run_transition(current_status, next_status)


def test_terminal_run_state_is_immutable():
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        conversation_id="conv-1",
        trace_id="trace-1",
        transport="chat",
        visibility="shadow",
        feature_mode="shadow",
        client_context_json={"_request_path": "/api/assistant/v2/runs"},
        status="completed",
    )
    service = FinnV2RunService(_FakeSession())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()

    with pytest.raises(InvalidRunTransitionError):
        asyncio.run(service.transition_run("run-1", 7, next_status="failed"))


def test_run_service_uses_nested_transaction_for_status_and_trace_atomicity():
    source = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")

    assert "async with self.session.begin_nested()" in source
    assert "await self.runs.update_status(" in source
    assert "await self.traces.append_event(" in source
    assert "await self.runs._commit_with_rollback(" in source


def test_create_run_commits_before_lifecycle_can_rollback():
    session = _FakeSession()
    service = FinnV2RunService(session)
    service.runs = _FakeRunRepo(None)
    service.runs.session = session
    service.traces = _FakeTraceRepo()
    service.conversations = _FakeConversationRepo()

    run = asyncio.run(
        service.create_run(
            {
                "id": "run-1",
                "conversation_id": "conv-1",
                "user_id": 7,
                "trace_id": "trace-1",
                "transport": "chat",
                "visibility": "visible",
                "feature_mode": "visible_runtime",
                "client_context_json": {"_request_path": "/api/assistant/chat"},
                "status": "created",
            }
        )
    )

    assert run.id == "run-1"
    assert session.commit_calls == 1
    assert service.conversations.last_run == {
        "conversation_id": "conv-1",
        "user_id": 7,
        "run_id": "run-1",
    }
    assert service.traces.events[0]["event_type"] == "run_created"


def test_visible_run_executes_orchestrator_without_shadow_gate():
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        conversation_id="conv-1",
        trace_id="trace-1",
        transport="chat",
        visibility="visible",
        feature_mode="visible_readonly",
        client_context_json={"_request_path": "/api/assistant/chat"},
        status="created",
    )
    service = FinnV2RunService(_FakeSession())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()

    calls = {"shadow_chain": 0, "placeholder": 0, "orchestrator": 0}

    async def _shadow_chain(**_kwargs):
        calls["shadow_chain"] += 1

    async def _placeholder(**_kwargs):
        calls["placeholder"] += 1

    async def _orchestrator(**kwargs):
        calls["orchestrator"] += 1
        assert kwargs["run_id"] == "run-1"
        assert kwargs["user_id"] == 7
        assert kwargs["trace_id"] == "trace-1"

    service.tools = SimpleNamespace(
        flags=SimpleNamespace(should_run_block4_shadow=lambda _user_id: False),
        execute_shadow_tool_chain=_shadow_chain,
    )
    service.complete_placeholder_run = _placeholder
    service.orchestrator = SimpleNamespace(execute_run=_orchestrator)

    asyncio.run(service.run_foundation_lifecycle(run_id="run-1", user_id=7))

    assert calls == {"shadow_chain": 0, "placeholder": 0, "orchestrator": 1}


def test_fail_run_rolls_back_inactive_session_before_transition(monkeypatch):
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        conversation_id="conv-1",
        trace_id="trace-1",
        transport="chat",
        visibility="visible",
        feature_mode="visible_readonly",
        client_context_json={"_request_path": "/api/assistant/chat"},
        status="planned",
    )
    session = _FakeSession(is_active=False)
    service = FinnV2RunService(session)
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()

    asyncio.run(
        service.fail_run(
            run_id="run-1",
            user_id=7,
            error_code="orchestrator_failed",
            error_message="tool_call_update_failed",
        )
    )

    assert session.rollback_calls == 1
    assert run.status == "failed"
