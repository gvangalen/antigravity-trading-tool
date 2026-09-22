from types import SimpleNamespace
import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

from backend.services.asset_catalog_service import AssetCatalogService
from backend.services.finn_v2_freshness_service import FinnV2FreshnessService
from backend.services.finn_v2_tool_redaction_service import FinnV2ToolRedactionService
from backend.services.finn_v2_tool_execution_service import FinnV2ToolExecutionService
from backend.schemas.finn_v2_orchestrator_schema import ToolPlan
from backend.domain.finn_v2_tools import ToolExecutionResult


class _FakeRunRepo:
    async def get_by_id_for_user(self, *, run_id, user_id):
        return SimpleNamespace(
            id=run_id,
            user_id=user_id,
            status="planned",
            trace_id="trace-1",
            message="Vat mijn setup Resolver Gate Setup samen.",
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
        self.commit_calls = 0

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

    async def commit(self):
        self.commit_calls += 1


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


def test_tool_execution_releases_primary_connection_around_durable_call_sessions(monkeypatch):
    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.persistence_session_factory = object()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "should_run_block3_shadow", lambda _user_id: False)

    events = []

    async def _create_tool_call(**_kwargs):
        events.append(("create", session.commit_calls))
        return SimpleNamespace(id=41), 41

    async def _complete_tool_call(**_kwargs):
        events.append(("complete", session.commit_calls))
        return SimpleNamespace(id=41), False

    service._create_tool_call = _create_tool_call
    service._complete_tool_call = _complete_tool_call
    service.profile_adapter.execute = lambda **_kwargs: asyncio.sleep(
        0,
        result={"data": {"ok": True}, "summary": {"title": "profile"}, "as_of": None},
    )

    result = asyncio.run(
        service.execute_tool(run_id="run-1", user_id=7, tool_name="read_profile", selector={})
    )

    assert result.success is True
    assert events == [("create", 1), ("complete", 2)]


def test_tool_execution_releases_connection_after_owner_scoped_selector_enrichment(monkeypatch):
    session = _FakeSession()
    service = FinnV2ToolExecutionService(session=session)
    service.runs = _FakeRunRepo()
    service.persistence_session_factory = object()
    service.traces = _FakeTraceRepo()
    monkeypatch.setattr(service.flags, "is_tool_registry_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_registry_readonly", lambda: True)
    monkeypatch.setattr(service.flags, "is_tool_call_logging_enabled", lambda: True)
    monkeypatch.setattr(service.flags, "should_run_block3_shadow", lambda _user_id: False)

    events = []

    async def _enrich(**_kwargs):
        events.append(("enrich", session.commit_calls))
        return {"setup_id": 8}

    async def _create_tool_call(**_kwargs):
        events.append(("create", session.commit_calls))
        return SimpleNamespace(id=42), 42

    async def _complete_tool_call(**_kwargs):
        events.append(("complete", session.commit_calls))
        return SimpleNamespace(id=42), False

    async def _dispatch_tool(**_kwargs):
        return {
            "data": {"setup_id": 8, "name": "Resolver Gate Setup"},
            "summary": {"setup_id": 8, "name": "Resolver Gate Setup"},
            "entity_type": "setup",
            "entity_id": 8,
            "as_of": None,
        }

    service.resolver.enrich_tool_selector_from_message = _enrich
    service._create_tool_call = _create_tool_call
    service._complete_tool_call = _complete_tool_call
    service._dispatch_tool = _dispatch_tool

    result = asyncio.run(
        service.execute_tool(
            run_id="run-1",
            user_id=7,
            tool_name="read_active_setup",
            selector={},
        )
    )

    assert result.success is True
    assert events == [("enrich", 0), ("create", 1), ("complete", 2)]


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


def test_setup_reads_use_the_workspace_setup_reference_without_overriding_selector_intent():
    run = SimpleNamespace(
        workspace_hints_json={"setup_id": 326},
        client_context_json={"setup_id": 999},
    )

    derived = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={}, tool_name="read_active_setup", run=run
    )
    explicit = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"setup_id": 777}, tool_name="read_active_setup", run=run
    )
    unrelated = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={}, tool_name="read_watchlist", run=run
    )
    explicit_strategy = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"strategy_id": 42}, tool_name="read_active_setup", run=run
    )
    explicit_bot = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"bot_name": "Safe Paper Bot"}, tool_name="read_active_setup", run=run
    )
    collection = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"asset": "BTC", "setup_collection_requested": True},
        tool_name="read_active_setup",
        run=run,
    )

    assert derived == {"setup_id": 326}
    assert explicit == {"setup_id": 777}
    assert unrelated == {}
    assert explicit_strategy == {"strategy_id": 42}
    assert explicit_bot == {"bot_name": "Safe Paper Bot"}
    assert collection == {"asset": "BTC", "setup_collection_requested": True}


def test_relation_ids_discard_stale_workspace_asset_for_canonical_reads():
    run = SimpleNamespace(
        workspace_hints_json={"asset": "BTC", "setup_id": 11},
        client_context_json={"asset": "BTC"},
    )

    strategy = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"asset": "BTC", "setup_id": 42, "strategy_id": 73},
        tool_name="read_linked_strategy",
        run=run,
    )
    bot = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"asset": "BTC", "bot_id": 91},
        tool_name="read_linked_bot",
        run=run,
    )
    asset = FinnV2ToolExecutionService._with_workspace_setup_reference(
        selector={"asset": "BTC", "strategy_id": 73},
        tool_name="read_active_asset",
        run=run,
    )

    assert strategy == {"setup_id": 42, "strategy_id": 73}
    assert bot == {"bot_id": 91}
    assert asset == {"strategy_id": 73}


def test_active_setup_read_resolves_the_single_owner_setup_without_a_workspace_asset(monkeypatch):
    service = FinnV2ToolExecutionService(session=_FakeSession())
    run = SimpleNamespace(workspace_hints_json={}, client_context_json={})
    service.resolver.resolve_setup = AsyncMock(
        return_value={
            "setup": {"id": 326, "name": "FINN DCA Flow", "symbol": "BTC"},
            "resolution_source": "single_user_setup",
        }
    )
    service.setup_adapter.execute = AsyncMock(return_value={"data": {"setup_id": 326}})

    result = asyncio.run(
        service._dispatch_tool(
            tool_name="read_active_setup",
            user_id=7,
            selector={},
            run=run,
            shared_state={},
        )
    )

    assert result == {"data": {"setup_id": 326}}
    service.resolver.resolve_setup.assert_awaited_once_with(user_id=7, selector={}, asset=None)
    service.setup_adapter.execute.assert_awaited_once_with(
        setup={"id": 326, "name": "FINN DCA Flow", "symbol": "BTC"},
        resolution_source="single_user_setup",
    )


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


def test_full_plan_reads_run_as_dependency_dag_with_isolated_sessions(monkeypatch):
    service = FinnV2ToolExecutionService(session=_FakeSession())
    service.persistence_session_factory = object()
    active = 0
    peak_active = 0
    started = {}
    completed = {}

    async def _execute_isolated(**kwargs):
        nonlocal active, peak_active
        name = kwargs["tool_name"]
        active += 1
        peak_active = max(peak_active, active)
        started[name] = asyncio.get_running_loop().time()
        await asyncio.sleep(0.05 if name == "read_technical_snapshot" else 0.01)
        completed[name] = asyncio.get_running_loop().time()
        active -= 1
        state = dict(kwargs["shared_state"])
        if name == "read_active_asset":
            state["asset"] = "BTC"
        elif name == "read_active_setup":
            state["setup"] = {"setup_id": 7}
        elif name == "read_linked_strategy":
            state["strategy"] = {"strategy_id": 8}
        elif name == "read_linked_bot":
            state["bot"] = {"bot_id": 9}
        return ToolExecutionResult(tool_name=name, status="completed", success=True), state

    monkeypatch.setattr(service, "_execute_tool_in_isolated_session", _execute_isolated)
    names = [
        "read_profile",
        "read_user_preferences",
        "read_active_asset",
        "read_indicator_configuration",
        "read_asset_scores",
        "read_market_snapshot",
        "read_macro_snapshot",
        "read_technical_snapshot",
        "read_active_setup",
        "read_linked_strategy",
        "read_linked_bot",
        "read_bot_status",
    ]
    plan = ToolPlan(
        run_id="run-plan",
        interaction_mode="EVALUATE",
        tool_names=names,
        tool_inputs={name: {"asset": "BTC"} for name in names},
        max_tool_calls=15,
    )

    results = asyncio.run(service.execute_tool_plan(run_id="run-plan", user_id=7, tool_plan=plan))

    assert [result.tool_name for result in results] == names
    assert peak_active >= 5
    assert started["read_indicator_configuration"] >= completed["read_active_asset"]
    assert started["read_linked_strategy"] >= completed["read_active_setup"]
    assert started["read_linked_bot"] >= completed["read_linked_strategy"]
    assert started["read_bot_status"] >= completed["read_linked_bot"]
    assert started["read_active_setup"] < completed["read_technical_snapshot"]


def test_isolated_tool_uses_one_atomic_session_without_nested_factory(monkeypatch):
    class _AtomicSession:
        def __init__(self):
            self.commit_calls = 0

        async def commit(self):
            self.commit_calls += 1

    class _FactoryContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *_args):
            return False

    outer = FinnV2ToolExecutionService(session=_FakeSession())
    atomic_session = _AtomicSession()
    outer.persistence_session_factory = lambda: _FactoryContext(atomic_session)

    async def _execute_tool(inner, **kwargs):
        assert inner.persistence_session_factory is None
        return ToolExecutionResult(
            tool_name=kwargs["tool_name"],
            status="completed",
            success=True,
        )

    monkeypatch.setattr(FinnV2ToolExecutionService, "execute_tool", _execute_tool)
    result, _state = asyncio.run(
        outer._execute_tool_in_isolated_session(
            run_id="run-atomic",
            user_id=7,
            tool_name="read_profile",
            selector={},
            shared_state={},
            operation_id="evaluate_plan",
            operation_contract_version="v1",
        )
    )

    assert result.success is True
    assert atomic_session.commit_calls == 1
