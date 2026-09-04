from pathlib import Path
from types import SimpleNamespace
import asyncio

import pytest

from backend.domain.finn_v2_contract import InvalidRunTransitionError, validate_run_transition
from backend.schemas.finn_v2_schema import AgentRunRequest
from backend.services import finn_v2_gateway_service as gateway_module
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

    def add(self, _row):
        pass


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


class _FakeRuntimeContracts:
    def __init__(self):
        self.calls = []

    async def create_for_run(self, *, run):
        self.calls.append(("create", run.id))
        return SimpleNamespace(contract_id=f"contract-{run.id}")

    async def record_lifecycle_status(self, *, run_id, status, mode):
        self.calls.append(("lifecycle", run_id, status, mode))

    async def materialize_terminal(self, **kwargs):
        self.calls.append(("terminal", kwargs["run_id"], kwargs["status"]))
        return SimpleNamespace(terminal_projection_json={"run_id": kwargs["run_id"], "terminal_status": kwargs["status"]})

    async def get_for_run(self, *, run_id):
        return None


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("created", "queued"),
        ("created", "failed"),
        ("created", "canceled"),
        ("queued", "collecting"),
        ("collecting", "planned"),
        ("collecting", "blocked"),
        ("collecting", "failed"),
        ("collecting", "canceled"),
        ("planned", "reasoning"),
        ("planned", "clarification_required"),
        ("planned", "unavailable"),
        ("planned", "completed"),
        ("planned", "blocked"),
        ("planned", "failed"),
        ("planned", "canceled"),
        ("reasoning", "verifying"),
        ("reasoning", "completed"),
        ("reasoning", "downgraded"),
        ("reasoning", "rejected"),
        ("reasoning", "unavailable"),
        ("reasoning", "failed"),
        ("verifying", "completed"),
        ("verifying", "downgraded"),
        ("verifying", "rejected"),
        ("verifying", "unavailable"),
    ],
)
def test_allowed_run_transitions(current_status, next_status):
    validate_run_transition(current_status, next_status)


@pytest.mark.parametrize(
    ("current_status", "next_status"),
    [
        ("created", "completed"),
        ("created", "collecting"),
        ("collecting", "completed"),
        ("blocked", "completed"),
        ("completed", "failed"),
        ("failed", "planned"),
        ("canceled", "collecting"),
        ("verifying", "reasoning"),
        ("rejected", "completed"),
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
    service.runtime_contracts = _FakeRuntimeContracts()

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
    service.runtime_contracts = _FakeRuntimeContracts()

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
    service.complete_run = _placeholder
    service.orchestrator = SimpleNamespace(
        execute_run=_orchestrator,
        consume_phase_outcome=lambda: SimpleNamespace(
            terminal_status="completed",
            interaction_mode="READ",
            orchestrator_result_id="orchestrator-1",
        ),
    )

    asyncio.run(service.run_foundation_lifecycle(run_id="run-1", user_id=7))

    assert calls == {"shadow_chain": 0, "placeholder": 1, "orchestrator": 1}
    assert service.session.commit_calls == 3


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
    service.runtime_contracts = _FakeRuntimeContracts()

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


class _FakeConversationRepo:
    def __init__(self, _session=None):
        self.rows = {}
        self.last_run = None

    async def get_by_id_for_user(self, conversation_id, user_id):
        row = self.rows.get(conversation_id)
        if row and row.user_id == user_id:
            return row
        return None

    async def create(self, *, conversation_id, user_id, title=None):
        row = SimpleNamespace(id=conversation_id, user_id=user_id, title=title)
        self.rows[conversation_id] = row
        return row

    async def set_last_run(self, *, conversation_id, user_id, run_id):
        self.last_run = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "run_id": run_id,
        }


class _FakeGatewayRunRepo:
    def __init__(self, _session):
        pass

    async def get_by_idempotency_key_for_user(self, *, idempotency_key, user_id):
        return None


class _FakeGatewayRunService:
    def __init__(self, _session):
        self.lifecycle_calls = []

    async def create_run(self, payload, *, commit=True):
        return SimpleNamespace(**payload)

    async def run_foundation_lifecycle(self, *, run_id, user_id):
        self.lifecycle_calls.append((run_id, user_id))


def test_gateway_run_foundation_now_returns_same_run_id_after_visible_budget_timeout(monkeypatch):
    monkeypatch.setattr(gateway_module, "FinnV2ConversationRepository", _FakeConversationRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunRepository", _FakeGatewayRunRepo)
    monkeypatch.setattr(gateway_module, "FinnV2RunService", _FakeGatewayRunService)
    monkeypatch.setattr(gateway_module.run_rate_limiter, "check_rate_limit", lambda *args, **kwargs: None)

    observed = []
    class _Dispatches:
        async def create(self, **kwargs):
            observed.append(("created", kwargs["run_id"]))
            return SimpleNamespace(task_id="task-1", queue="ai_generation", dispatch_id="dispatch-1")
        async def get_for_run(self, _run_id):
            return SimpleNamespace(task_id="task-1", queue="ai_generation", dispatch_id="dispatch-1")
        async def mark_published(self, dispatch_id):
            observed.append(("published", dispatch_id))
    class _Task:
        def apply_async(self, **kwargs):
            observed.append(kwargs)
    import backend.celery_task.finn_v2_task as task_module
    monkeypatch.setattr(task_module, "process_finn_v2_run", _Task())

    session = _FakeSession()
    service = gateway_module.FinnV2GatewayService(session=session)
    service.dispatches = _Dispatches()
    monkeypatch.setattr(service.flags, "resolve_mode", lambda _user_id: "visible_runtime")
    monkeypatch.setattr(service.flags, "allows_transport", lambda _transport: True)
    monkeypatch.setattr(service.flags, "max_runs_per_minute", lambda: 20)
    monkeypatch.setattr(service.flags, "visible_request_timeout_seconds", lambda _mode=None: 0)

    async def _exercise():
        run_id = await service.run_foundation_now(
            user_id=7,
            request_payload=AgentRunRequest(message="BTC graag", transport="chat").dict(),
            request_path="/api/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
        return run_id

    run_id = asyncio.run(_exercise())

    assert run_id.startswith("finn-v2-run-")
    assert session.commit_calls == 2
    assert observed == [
        ("created", run_id),
        {"kwargs": {"run_id": run_id}, "task_id": "task-1", "queue": "ai_generation"},
        ("published", "dispatch-1"),
    ]
