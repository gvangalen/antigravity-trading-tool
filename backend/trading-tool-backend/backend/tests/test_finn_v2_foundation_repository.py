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
    def begin_nested(self):
        return _NestedTxn()


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


class _FakeTraceRepo:
    def __init__(self):
        self.events = []

    async def append_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


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
    assert ".commit(" not in source
