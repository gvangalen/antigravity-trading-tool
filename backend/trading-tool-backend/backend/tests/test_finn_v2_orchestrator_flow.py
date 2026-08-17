import asyncio
from types import SimpleNamespace

from backend.schemas.finn_v2_domain_validation_schema import EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService


class _FakeRunRepo:
    def __init__(self, run):
        self.run = run

    async def get_by_id_for_user(self, *, run_id, user_id):
        if self.run.id == run_id and self.run.user_id == user_id:
            return self.run
        return None


class _FakeTraceRepo:
    def __init__(self):
        self.events = []

    async def append_event(self, **kwargs):
        self.events.append(kwargs)
        return kwargs


class _FakeResultRepo:
    def __init__(self):
        self.created = []

    async def get_for_run_version(self, **_kwargs):
        return None

    async def create(self, **kwargs):
        self.created.append(kwargs)
        return kwargs


async def _complete_placeholder(**kwargs):
    return kwargs


def test_orchestrator_flow_executes_plan_persists_result_and_completes_placeholder():
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        trace_id="trace-1",
        status="planned",
        message="Welke setup gebruik ik voor BTC?",
        workspace_hints_json={},
        client_context_json={},
    )
    service = FinnV2OrchestratorService(session=object(), complete_placeholder=_complete_placeholder)
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()
    service.results = _FakeResultRepo()
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_state_assembly_enabled = lambda: True

    captured = {}

    async def _execute_tool_plan(**kwargs):
        captured["tool_plan"] = kwargs["tool_plan"]
        return []

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-1",
                "snapshot_id": "snapshot-1",
                "run_id": "run-1",
                "user_id": 7,
                "evidence_set_hash": "hash",
                "integrity_status": "valid",
                "domains": [
                    {"domain": "plan_context", "status": "available", "confidence": "high"},
                ],
                "issues": [],
                "validated_at": "2026-08-17T10:00:00+00:00",
            }
        )
        return SimpleNamespace(snapshot_id="snapshot-1"), validation

    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline

    result = asyncio.run(service.execute_run(run_id="run-1", user_id=7, trace_id="trace-1"))

    assert isinstance(result, OrchestratorResult)
    assert result.outcome == "reasoning_ready"
    assert captured["tool_plan"].tool_names[0] == "read_active_asset"
    assert service.results.created[0]["outcome"] == "reasoning_ready"
    assert [event["event_type"] for event in service.traces.events] == [
        "orchestrator_started",
        "orchestrator_completed",
    ]
