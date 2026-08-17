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


def test_orchestrator_flow_executes_plan_and_persists_result():
    run = SimpleNamespace(
        id="run-1",
        user_id=7,
        trace_id="trace-1",
        status="planned",
        message="Welke setup gebruik ik voor BTC?",
        workspace_hints_json={},
        client_context_json={},
    )
    service = FinnV2OrchestratorService(session=object())
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
        return SimpleNamespace(id="snapshot-1", snapshot_id="snapshot-1", user_id=7), validation

    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            policy_class="read",
            allowed=True,
            proposal_input_required=False,
            blocking_codes=[],
        ),
    )
    service.policy.persist = lambda *args, **kwargs: asyncio.sleep(0, result=None)
    service.reasoning.reason = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(status="ready"))
    service.verifier.verify_run = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(mode="FACT", verifier_status="passed"))

    result = asyncio.run(service.execute_run(run_id="run-1", user_id=7, trace_id="trace-1"))

    assert isinstance(result, OrchestratorResult)
    assert result.outcome == "reasoning_ready"
    assert captured["tool_plan"].tool_names[0] == "read_active_asset"
    assert service.results.created[0]["outcome"] == "reasoning_ready"
    assert [event["event_type"] for event in service.traces.events] == [
        "orchestrator_started",
        "policy_evaluation_started",
        "policy_evaluation_completed",
        "orchestrator_completed",
    ]


def test_orchestrator_runs_policy_reasoning_and_verifier_for_visible_run_without_shadow_flags():
    run = SimpleNamespace(
        id="run-2",
        user_id=7,
        trace_id="trace-2",
        status="planned",
        visibility="visible",
        feature_mode="visible_readonly",
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
    service.flags.should_run_block5_shadow = lambda _user_id: False
    service.flags.should_run_block6_shadow = lambda _user_id: False
    service.flags.should_run_block7_shadow = lambda _user_id: False

    captured = {"policy": 0, "reasoning": 0, "verifier": 0}

    async def _execute_tool_plan(**kwargs):
        captured["tool_plan"] = kwargs["tool_plan"]
        return []

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-2",
                "snapshot_id": "snapshot-2",
                "run_id": "run-2",
                "user_id": 7,
                "evidence_set_hash": "hash-2",
                "integrity_status": "valid",
                "domains": [
                    {"domain": "plan_context", "status": "available", "confidence": "high"},
                ],
                "issues": [],
                "validated_at": "2026-08-17T10:00:00+00:00",
            }
        )
        return SimpleNamespace(snapshot_id="snapshot-2"), validation

    async def _evaluate_run(**_kwargs):
        captured["policy"] += 1
        return SimpleNamespace(
            policy_class="read",
            allowed=True,
            proposal_input_required=False,
            blocking_codes=[],
        )

    async def _persist_policy(*_args, **_kwargs):
        return None

    async def _reason(**_kwargs):
        captured["reasoning"] += 1
        return SimpleNamespace(status="completed")

    async def _verify_run(**_kwargs):
        captured["verifier"] += 1
        return SimpleNamespace(mode="FACT", verifier_status="passed")

    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = _evaluate_run
    service.policy.persist = _persist_policy
    service.reasoning.reason = _reason
    service.verifier.verify_run = _verify_run

    result = asyncio.run(service.execute_run(run_id="run-2", user_id=7, trace_id="trace-2"))

    assert isinstance(result, OrchestratorResult)
    assert result.outcome == "reasoning_ready"
    assert captured["tool_plan"].tool_names[0] == "read_active_asset"
    assert captured["policy"] == 1
    assert captured["reasoning"] == 1
    assert captured["verifier"] == 1
