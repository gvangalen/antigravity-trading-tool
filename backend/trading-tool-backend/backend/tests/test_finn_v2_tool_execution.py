from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService


class _FakeRunRepo:
    async def get_by_id_for_user(self, *, run_id, user_id):
        return SimpleNamespace(
            id=run_id,
            user_id=user_id,
            status="planned",
            trace_id="trace-1",
            workspace_hints_json={},
            client_context_json={},
        )


class _FakeCallRepo:
    def __init__(self):
        self.rows = []

    async def create(self, **kwargs):
        row = SimpleNamespace(**kwargs)
        self.rows.append(row)
        return row

    async def update(self, row, **kwargs):
        for key, value in kwargs.items():
            setattr(row, key, value)
        return row


class _FakeTraceRepo:
    async def append_event(self, **kwargs):
        return kwargs


def test_tool_execution_returns_feature_disabled_when_registry_off(monkeypatch):
    service = FinnV2ToolExecutionService(session=object())
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: False)

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.error_codes == ["tool_feature_disabled"]


def test_tool_execution_logs_successful_profile_call(monkeypatch):
    service = FinnV2ToolExecutionService(session=object())
    service.runs = _FakeRunRepo()
    service.calls = _FakeCallRepo()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    service.profile_adapter.execute = lambda **_kwargs: asyncio.sleep(0, result={"data": {"ok": True}, "summary": {"title": "profile"}, "as_of": None})

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.success is True
    assert service.calls.rows[-1].status == "completed"


def test_state_pipeline_rolls_back_before_failure_trace():
    class _Session:
        def __init__(self):
            self.rollback_calls = 0

        async def rollback(self):
            self.rollback_calls += 1

    class _TraceRepo:
        def __init__(self):
            self.events = []

        async def append_event(self, **kwargs):
            self.events.append(kwargs)
            return kwargs

    service = FinnV2ToolExecutionService(session=_Session())
    service.runs = _FakeRunRepo()
    service.traces = _TraceRepo()

    async def _explode(**_kwargs):
        raise TypeError("Object of type datetime is not JSON serializable")

    service.snapshots.assemble_for_run = _explode

    snapshot, validation = asyncio.run(service.run_state_pipeline(run_id="run-1", user_id=7))

    assert snapshot is None
    assert validation is None
    assert service.session.rollback_calls == 1
    assert [event["event_type"] for event in service.traces.events] == [
        "state_assembly_started",
        "state_assembly_failed",
    ]


def test_asset_catalog_fallback_does_not_require_session_rollback():
    service = AssetCatalogService(AsyncMock())

    class _Repo:
        async def get_assets(self, _symbols):
            raise RuntimeError("extended read failed")

    service.repository = _Repo()

    result = asyncio.run(service.get_assets(["BTC"]))

    service.session.rollback.assert_not_awaited()
    assert result["BTC"]["symbol"] == "BTC"
