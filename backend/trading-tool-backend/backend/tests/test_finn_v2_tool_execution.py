from types import SimpleNamespace
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
from backend.services.finn_v2_tool_redaction_service import FinnV2ToolRedactionService
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


class _FailingUpdateCallRepo(_FakeCallRepo):
    async def update(self, row, **kwargs):
        raise RuntimeError("tool_call_flush_failed")


class _FakeTraceRepo:
    async def append_event(self, **kwargs):
        return kwargs


class _CollectingTraceRepo:
    def __init__(self):
        self.events = []

    async def append_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


class _NestedTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSession:
    def __init__(self):
        self.sync_session = SimpleNamespace(is_active=True)
        self._transaction = SimpleNamespace(is_active=True)
        self.rollback_calls = 0

    def begin_nested(self):
        return _NestedTxn()

    def in_transaction(self):
        return True

    def get_transaction(self):
        return self._transaction

    async def rollback(self):
        self.rollback_calls += 1
        self.sync_session.is_active = True
        self._transaction.is_active = True


@dataclass
class _ComplexSummary:
    symbol: str
    captured_at: datetime


def test_tool_execution_returns_feature_disabled_when_registry_off(monkeypatch):
    service = FinnV2ToolExecutionService(session=object())
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: False)

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.error_codes == ["tool_feature_disabled"]


def test_tool_execution_logs_successful_profile_call(monkeypatch):
    service = FinnV2ToolExecutionService(session=_FakeSession())
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


def test_tool_execution_dispatches_watchlist_adapter(monkeypatch):
    service = FinnV2ToolExecutionService(session=_FakeSession())
    service.runs = _FakeRunRepo()
    service.calls = _FakeCallRepo()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    service.asset_adapter.execute = lambda **_kwargs: asyncio.sleep(
        0,
        result={
            "data": {"asset": "ETH"},
            "summary": {"title": "active_asset", "symbol": "ETH"},
            "resolution_source": "selector",
            "entity_type": "asset",
            "entity_id": "ETH",
            "asset": "ETH",
            "as_of": None,
        },
    )
    service.watchlist_adapter.execute = lambda **_kwargs: asyncio.sleep(
        0,
        result={
            "data": {"target_asset": "ETH", "contains_target_asset": False, "symbols": []},
            "summary": {"target_asset": "ETH", "contains_target_asset": False, "symbol_count": 0},
            "resolution_source": "user_watchlist",
            "entity_type": "watchlist",
            "entity_id": "7",
            "asset": "ETH",
            "as_of": None,
        },
    )

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_watchlist", selector={"asset": "ETH"}))

    assert result.success is True
    assert result.result["target_asset"] == "ETH"
    assert result.result["contains_target_asset"] is False
    assert service.calls.rows[-1].tool_name == "read_watchlist"
    assert service.calls.rows[-1].status == "completed"


def test_tool_redaction_service_serializes_nested_objects():
    service = FinnV2ToolRedactionService()

    payload = service.redact_result_summary(
        {
            "snapshot": _ComplexSummary(symbol="BTC", captured_at=datetime(2026, 8, 18, 10, 30, tzinfo=timezone.utc)),
            "items": [_ComplexSummary(symbol="AAPL", captured_at=datetime(2026, 8, 18, 11, 0, tzinfo=timezone.utc))],
        }
    )

    assert payload["snapshot"]["symbol"] == "BTC"
    assert payload["snapshot"]["captured_at"] == "2026-08-18T10:30:00+00:00"
    assert payload["items"][0]["symbol"] == "AAPL"


def test_complete_tool_call_uses_captured_id_when_update_fails(monkeypatch):
    service = FinnV2ToolExecutionService(session=_FakeSession())
    service.calls = _FailingUpdateCallRepo()

    result, rolled_back = asyncio.run(
        service._complete_tool_call(
            tool_call=SimpleNamespace(id=77),
            tool_call_id=77,
            result=SimpleNamespace(
                tool_name="read_profile",
                status="completed",
                success=True,
                resolution_source=None,
                freshness_status="fresh",
                result_summary={"ok": True},
                error_codes=[],
            ),
            duration_ms=5,
            run_id="run-1",
            user_id=7,
            trace_id="trace-1",
        )
    )

    assert result is None
    assert rolled_back is True


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


def test_asset_catalog_fallback_rolls_back_failed_session():
    service = AssetCatalogService(AsyncMock())

    class _Repo:
        async def get_assets(self, _symbols):
            raise RuntimeError("extended read failed")

    service.repository = _Repo()

    result = asyncio.run(service.get_assets(["BTC"]))

    service.session.rollback.assert_awaited_once()
    assert result["BTC"]["symbol"] == "BTC"


def test_freshness_service_accepts_date_values_for_daily_tools():
    service = FinnV2FreshnessService()

    freshness = service.freshness_for("read_asset_scores", date.today())

    assert freshness in {"fresh", "stale"}


def test_tool_execution_rolls_back_failed_session_before_tool_call_completion(monkeypatch):
    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.calls = _FakeCallRepo()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)

    async def _explode(**_kwargs):
        session.sync_session.is_active = False
        session.get_transaction().is_active = False
        raise RuntimeError("db_read_failed")

    service.profile_adapter.execute = _explode

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.success is False
    assert result.error_codes == ["tool_internal_error"]
    assert session.rollback_calls == 1


def test_tool_timeout_rolls_back_before_evidence_reuses_session(monkeypatch):
    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.calls = _FakeCallRepo()
    service.traces = _FakeTraceRepo()
    service.evidence.ingest_tool_result = AsyncMock(side_effect=AssertionError("timeout must skip evidence ingestion"))
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "should_run_block3_shadow", lambda _user_id: True)

    async def _hang(**_kwargs):
        await asyncio.sleep(0.01)

    service.profile_adapter.execute = _hang

    result = asyncio.run(
        service.execute_tool(
            run_id="run-1",
            user_id=7,
            tool_name="read_profile",
            selector={},
            timeout_seconds=0.001,
        )
    )

    assert result.success is False
    assert result.error_codes == ["tool_timeout"]
    assert session.rollback_calls == 1
    assert service.evidence.ingest_tool_result.await_count == 0


def test_tool_execution_rolls_back_poisoned_session_before_next_tool_call(monkeypatch):
    session = _FakeSession()
    session.sync_session.is_active = False
    session.get_transaction().is_active = False
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.calls = _FakeCallRepo()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    service.profile_adapter.execute = lambda **_kwargs: asyncio.sleep(
        0,
        result={"data": {"ok": True}, "summary": {"title": "profile"}, "as_of": None},
    )

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.success is True
    assert session.rollback_calls == 1
    assert service.calls.rows[-1].status == "completed"


def test_evidence_ingestion_rolls_back_poisoned_session(monkeypatch):
    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "should_run_block3_shadow", lambda _user_id: True)

    async def _explode(**_kwargs):
        session.sync_session.is_active = False
        session.get_transaction().is_active = False
        raise RuntimeError("artifact_flush_failed")

    service.evidence.ingest_tool_result = _explode

    result = SimpleNamespace(
        tool_name="read_profile",
        status="completed",
        success=True,
        selector={},
        result={"ok": True},
        result_summary={"title": "profile"},
        resolution_source=None,
        freshness_status="fresh",
        error_codes=[],
        source="internal",
        schema_name="read_profile",
        schema_version="2026-08-17.block2",
        availability="available",
        entity_type="profile",
        entity_id=None,
        asset=None,
        tool_call_id=12,
    )

    asyncio.run(service._ingest_evidence(run_id="run-1", user_id=7, trace_id="trace-1", result=result))

    assert session.rollback_calls == 1


def test_tool_execution_skips_evidence_ingestion_after_tool_call_completion_rollback(monkeypatch):
    class _PoisoningUpdateCallRepo(_FakeCallRepo):
        def __init__(self, session):
            super().__init__()
            self.session = session

        async def update(self, row, **kwargs):
            self.session.sync_session.is_active = False
            self.session.get_transaction().is_active = False
            raise RuntimeError("tool_call_flush_failed")

    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.calls = _PoisoningUpdateCallRepo(session)
    service.traces = _CollectingTraceRepo()
    service.evidence.ingest_tool_result = AsyncMock(side_effect=AssertionError("evidence ingestion should be skipped"))
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "should_run_block3_shadow", lambda _user_id: True)
    service.profile_adapter.execute = lambda **_kwargs: asyncio.sleep(
        0,
        result={"data": {"ok": True}, "summary": {"title": "profile"}, "as_of": None},
    )

    result = asyncio.run(service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={}))

    assert result.success is True
    assert session.rollback_calls == 1
    assert service.evidence.ingest_tool_result.await_count == 0
    assert service.traces.events == []
