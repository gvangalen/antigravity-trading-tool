import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_domain_validation_schema import EvidenceValidationResult
from backend.services.finn_v2_domain_requirement_service import FinnV2DomainRequirementService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_request_analysis_service import FinnV2RequestAnalysisService


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


def test_incomplete_trade_question_has_no_required_domains():
    analysis = FinnV2RequestAnalysisService().analyze(
        message="Wat is nu de beste trade voor mij zonder verdere context?"
    )

    plan = FinnV2DomainRequirementService().determine(analysis)

    assert analysis.interaction_mode == "UNAVAILABLE"
    assert plan.required_domains == []
    assert plan.requirement_reason == ["deterministic_unavailable_without_provider_call"]


def test_incomplete_trade_route_avoids_provider_and_returns_unavailable():
    run = SimpleNamespace(
        id="run-fast-1",
        user_id=7,
        trace_id="trace-fast-1",
        status="planned",
        visibility="visible",
        feature_mode="visible_readonly",
        message="Wat is nu de beste trade voor mij zonder verdere context?",
        workspace_hints_json={},
        client_context_json={"surface": "assistant_visible_v2"},
    )
    service = FinnV2OrchestratorService(session=object())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()
    service.results = _FakeResultRepo()
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_state_assembly_enabled = lambda: True

    calls = {"tools": 0, "policy": 0, "reasoning": 0, "verifier": 0}

    async def _execute_tool_plan(**kwargs):
        calls["tools"] += 1
        assert kwargs["tool_plan"].tool_names == []
        return []

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-fast-1",
                "snapshot_id": "snapshot-fast-1",
                "run_id": "run-fast-1",
                "user_id": 7,
                "evidence_set_hash": "hash-fast-1",
                "integrity_status": "valid",
                "domains": [],
                "issues": [],
                "validated_at": "2026-08-18T10:00:00+00:00",
            }
        )
        return SimpleNamespace(snapshot_id="snapshot-fast-1"), validation

    async def _evaluate_run(**_kwargs):
        calls["policy"] += 1
        return SimpleNamespace(
            policy_class="read",
            allowed=True,
            proposal_input_required=False,
            blocking_codes=[],
            policy_decision_id="policy-fast-1",
        )

    async def _persist_policy(*_args, **_kwargs):
        return None

    async def _reason(**_kwargs):
        calls["reasoning"] += 1
        return SimpleNamespace(status="unavailable", mode="UNAVAILABLE")

    async def _verify_run(**_kwargs):
        calls["verifier"] += 1
        return SimpleNamespace(mode="UNAVAILABLE", verifier_status="passed")

    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = _evaluate_run
    service.policy.persist = _persist_policy
    service.reasoning.reason = _reason
    service.verifier.verify_run = _verify_run

    result = asyncio.run(service.execute_run(run_id="run-fast-1", user_id=7, trace_id="trace-fast-1"))

    assert result.outcome == "unavailable"
    assert "insufficient_trade_context" in result.unavailable_codes
    assert calls == {"tools": 1, "policy": 1, "reasoning": 1, "verifier": 1}


def test_gateway_marks_visible_timeout_as_terminal_failure():
    from backend.services.finn_v2_gateway_service import FinnV2GatewayService

    service = FinnV2GatewayService(session=object())
    service.flags.visible_request_timeout_seconds = lambda: 1
    service.create_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-timeout-1", status="created"))

    observed = {"failed": None}

    async def _slow_lifecycle(**_kwargs):
        await asyncio.sleep(2)

    async def _fail_run(**kwargs):
        observed["failed"] = kwargs

    service.run_service.run_foundation_lifecycle = _slow_lifecycle
    service.run_service.fail_run = _fail_run

    run_id = asyncio.run(
        service.run_foundation_now(
            user_id=7,
            request_payload={"message": "Wat is nu de beste trade voor mij zonder verdere context?", "transport": "chat"},
            request_path="/api/assistant/chat",
            request_id="req-timeout-1",
            trace_id="trace-timeout-1",
        )
    )

    assert run_id == "run-timeout-1"
    assert observed["failed"]["run_id"] == "run-timeout-1"
    assert observed["failed"]["error_code"] == "visible_request_timeout"
    assert observed["failed"]["failure_stage"] == "visible_request_timeout"
    assert isinstance(observed["failed"]["primary_exception"], TimeoutError)


def test_visible_request_timeout_default_covers_live_plan_budget():
    from backend.services.finn_v2_flag_service import FinnV2FlagService

    assert FinnV2FlagService().visible_request_timeout_seconds() == 20


def test_gateway_cancels_run_when_request_is_cancelled():
    from backend.services.finn_v2_gateway_service import FinnV2GatewayService

    service = FinnV2GatewayService(session=object())
    service.create_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="run-cancel-1", status="created"))

    observed = {"canceled": None}

    lifecycle_started = asyncio.Event()

    async def _never_finish(**_kwargs):
        lifecycle_started.set()
        await asyncio.sleep(30)

    async def _cancel_run(**kwargs):
        observed["canceled"] = kwargs

    service.run_service.run_foundation_lifecycle = _never_finish
    service.run_service.cancel_run = _cancel_run

    async def _invoke():
        task = asyncio.create_task(
            service.run_foundation_now(
                user_id=7,
                request_payload={"message": "Wat is nu de beste trade voor mij zonder verdere context?", "transport": "chat"},
                request_path="/api/assistant/chat",
                request_id="req-cancel-1",
                trace_id="trace-cancel-1",
            )
        )
        await lifecycle_started.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return
        raise AssertionError("expected request cancellation")

    asyncio.run(_invoke())

    assert observed["canceled"]["run_id"] == "run-cancel-1"
