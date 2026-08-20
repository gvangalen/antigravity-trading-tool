import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_reasoning_context_schema import (
    ReasoningContextPackage,
    ReasoningDomainStatus,
    ReasoningEvidenceItem,
    ReasoningPolicyContext,
)
from backend.schemas.finn_v2_reasoning_schema import ReasoningResult
from backend.services.finn_v2_reasoning_fallback_service import FinnV2ReasoningFallbackService
from backend.services.finn_v2_reasoning_service import FinnV2ReasoningService
from backend.services.finn_v2_reasoning_prompt_service import FinnV2ReasoningPromptContractError


def test_reasoning_unavailable_when_ai_disabled(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(id="run-1", user_id=7, message="Welke setup gebruik ik?", client_context_json={}, workspace_hints_json={})
    orchestrator_row = SimpleNamespace(
        id="orchestrator-1",
        run_id="run-1",
        user_id=7,
        interaction_mode="FACT",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["setup"],
        required_domains_json=["plan_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-1", "interaction_mode": "FACT", "max_tool_calls": 15},
        snapshot_id="snapshot-1",
        validation_id="validation-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
            created_at=datetime.now(timezone.utc),
        )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-1", snapshot_id="snapshot-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-1", validation_id="validation-1", integrity_status="valid", evidence_set_hash="hash", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(decision_json={"policy_decision_id": "policy-1", "run_id": "run-1", "user_id": 7, "policy_class": "read", "allowed": True, "proposal_allowed": False, "confirmation_required": False, "step_up_required": False, "execution_allowed": False, "shadow_safe": True, "created_at": "2026-08-17T10:00:00+00:00"}))
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="FACT", context_version="2026-08-17.block6", evidence_set_hash="hash", evidence=[], subject_scopes=[], required_domains=[], dict=lambda : {},))
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    service._persist_record = lambda **kwargs: asyncio.sleep(0, result=kwargs)
    monkeypatch.setattr(service.flags, "should_run_block6_shadow", lambda _user_id: False)

    result = asyncio.run(service.reason(user_id=7, run_id="run-1", trace_id="trace-1"))

    assert result["status"] == "unavailable"


def test_visible_reasoning_bypasses_shadow_gate_when_runtime_is_live(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-2",
        user_id=7,
        message="Welke setup gebruik ik?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-2",
        run_id="run-2",
        user_id=7,
        interaction_mode="FACT",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["setup"],
        required_domains_json=["plan_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-2", "interaction_mode": "FACT", "max_tool_calls": 15},
        snapshot_id="snapshot-2",
        validation_id="validation-2",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-2", snapshot_id="snapshot-2"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-2", validation_id="validation-2", integrity_status="valid", evidence_set_hash="hash", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(decision_json={"policy_decision_id": "policy-2", "run_id": "run-2", "user_id": 7, "policy_class": "read", "allowed": True, "proposal_allowed": False, "confirmation_required": False, "step_up_required": False, "execution_allowed": False, "shadow_safe": True, "created_at": "2026-08-17T10:00:00+00:00"}))
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(interaction_mode="FACT", context_version="2026-08-17.block6", evidence_set_hash="hash", evidence=[], subject_scopes=[], required_domains=[], dict=lambda: {}))
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    service._run_model_reasoning = lambda **_kwargs: asyncio.sleep(0, result="model-called")
    monkeypatch.setattr(service.flags, "should_run_block6_shadow", lambda _user_id: False)
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True, "model": "gpt-test"})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})

    result = asyncio.run(service.reason(user_id=7, run_id="run-2", trace_id="trace-2"))

    assert result == "model-called"


def test_reasoning_uses_grounded_evaluation_fallback_on_provider_error(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-eval-1",
        user_id=7,
        message="Bekijk mijn BTC plan.",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "BTC"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-eval-1",
        run_id="run-eval-1",
        user_id=7,
        interaction_mode="EVALUATION",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["profile", "indicators", "setup", "strategy", "bot"],
        required_domains_json=["identity_context", "market_context", "plan_context", "automation_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-eval-1", "interaction_mode": "EVALUATION", "max_tool_calls": 15},
        snapshot_id="snapshot-eval-1",
        validation_id="validation-eval-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=["provider_error"],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-eval-1", snapshot_id="snapshot-eval-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-eval-1", validation_id="validation-eval-1", integrity_status="valid", evidence_set_hash="hash-eval", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-eval-1",
                "run_id": "run-eval-1",
                "user_id": 7,
                "policy_class": "advice",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
                "shadow_safe": True,
                "created_at": "2026-08-18T10:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-eval-1",
        user_id=7,
        user_message="Bekijk mijn BTC plan.",
        locale="nl-NL",
        interaction_mode="EVALUATION",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"],
        required_domains=["identity_context", "market_context", "plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-eval-1",
        snapshot_id="snapshot-eval-1",
        validation_id="validation-eval-1",
        policy_decision_id="policy-eval-1",
        evidence_set_hash="hash-eval",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_profile",
                domain="identity_context",
                entity_type="profile",
                source="internal",
                freshness="not_applicable",
                confidence="high",
                facts={"has_profile": False, "trader_profile": {}},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_indicator_configuration",
                domain="market_context",
                entity_type="indicator_configuration",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"symbol": "BTC", "configured_indicators": []},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_active_setup",
                domain="plan_context",
                entity_type="setup",
                entity_id="282",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"setup_id": 282, "symbol": "BTC", "timeframe": "4H"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E4",
                artifact_id="a4",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="298",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"strategy_id": 298, "setup_id": 282, "symbol": "BTC", "execution_mode": "fixed", "risk_profile": None},
            ),
            ReasoningEvidenceItem(
                evidence_id="E5",
                artifact_id="a5",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="159",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"bot_id": 159, "strategy_id": 298, "is_live": False, "is_active": True},
            ),
            ReasoningEvidenceItem(
                evidence_id="E6",
                artifact_id="a6",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="159",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"bot_id": 159, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[
            ReasoningDomainStatus(domain="identity_context", status="available", confidence="high"),
            ReasoningDomainStatus(domain="market_context", status="available", confidence="medium", issue_codes=["provider_error"]),
            ReasoningDomainStatus(domain="plan_context", status="available", confidence="high"),
            ReasoningDomainStatus(domain="automation_context", status="available", confidence="high"),
        ],
        policy=ReasoningPolicyContext(
            policy_class="advice",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        allowed_response_modes=["EVALUATION", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=["provider_error"],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    persisted = {}

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"error": "provider_error"},
    )

    result = asyncio.run(service.reason(user_id=7, run_id="run-eval-1", trace_id="trace-eval-1"))

    assert result["status"] == "ready"
    assert result["mode"] == "EVALUATE"
    assert "BTC-plan" in result["result"].direct_answer
    assert result["result"].next_step is not None
    assert set(result["result"].evidence_refs_used) == {"E1", "E2", "E3", "E4", "E5", "E6"}


def test_reasoning_persistence_serializes_datetime_payloads():
    service = FinnV2ReasoningService(session=object())
    captured = {}

    async def _create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(created_at=datetime.now(timezone.utc), **kwargs)

    service.reasoning.create = _create
    result = ReasoningResult(
        reasoning_result_id="reasoning-3",
        run_id="run-3",
        user_id=7,
        mode="UNAVAILABLE",
        direct_answer="Niet beschikbaar.",
        main_observation="Reasoning is tijdelijk niet beschikbaar.",
        supporting_points=[],
        claims=[],
        uncertainty_summary=None,
        uncertainty_codes=[],
        next_step=None,
        follow_up_question=None,
        proposal_candidate=None,
        evidence_refs_used=[],
        model="gpt-test",
        created_at=datetime.now(timezone.utc),
    )

    persisted = asyncio.run(
        service._persist_record(
            run_id="run-3",
            user_id=7,
            orchestrator_result_id="orchestrator-3",
            policy_decision_id="policy-3",
            snapshot_id="snapshot-3",
            validation_id="validation-3",
            status="unavailable",
            mode="UNAVAILABLE",
            context_version="2026-08-17.block6",
            evidence_set_hash="hash-3",
            input_hash="input-3",
            model="gpt-test",
            result=result,
            error_codes=["ai_unavailable_configuration"],
            retry_count=0,
        )
    )

    assert isinstance(captured["result_json"]["created_at"], str)
    assert persisted.result.created_at == result.created_at


def test_reasoning_returns_failed_unavailable_record_on_prompt_contract_error(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    context = SimpleNamespace(
        interaction_mode="UNAVAILABLE",
        context_version="2026-08-17.block6",
        evidence_set_hash="hash-4",
        evidence=[],
        subject_scopes=[],
        required_domains=[],
        dict=lambda: {},
    )
    orchestrator_result = SimpleNamespace(orchestrator_result_id="orchestrator-4")
    policy = SimpleNamespace(policy_decision_id="policy-4")
    snapshot = SimpleNamespace(id="snapshot-4")
    validation = SimpleNamespace(id="validation-4")
    service._append_trace = lambda *args, **kwargs: asyncio.sleep(0, result=None)
    persisted_calls = {}

    async def _persist_record(**kwargs):
        persisted_calls.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(
        service.prompts,
        "build_system_prompt",
        lambda _context: (_ for _ in ()).throw(FinnV2ReasoningPromptContractError("FUTURE_MODE")),
    )

    result = asyncio.run(
        service._run_model_reasoning(
            run_id="run-4",
            user_id=7,
            trace_id="trace-4",
            orchestrator_result=orchestrator_result,
            policy=policy,
            snapshot=snapshot,
            validation=validation,
            context=context,
            model_name="gpt-test",
            input_hash="input-4",
        )
    )

    assert result["status"] == "failed"
    assert persisted_calls["error_codes"] == ["reasoning_prompt_mode_unsupported"]
    assert persisted_calls["mode"] == "UNAVAILABLE"
    assert persisted_calls["run_id"] == "run-4"


def test_reasoning_uses_grounded_read_fallback_on_incomplete_structured_response(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-read-1",
        user_id=7,
        message="Welke bot is aan mijn BTC-strategie gekoppeld, en staat deze bot momenteel live?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "BTC"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-read-1",
        run_id="run-read-1",
        user_id=7,
        interaction_mode="READ",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["strategy", "bot"],
        required_domains_json=["plan_context", "automation_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-read-1", "interaction_mode": "READ", "max_tool_calls": 15},
        snapshot_id="snapshot-read-1",
        validation_id="validation-read-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-read-1", snapshot_id="snapshot-read-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-read-1", validation_id="validation-read-1", integrity_status="valid", evidence_set_hash="hash-read", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-read-1",
                "run_id": "run-read-1",
                "user_id": 7,
                "policy_class": "read",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
                "shadow_safe": True,
                "created_at": "2026-08-18T10:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-read-1",
        user_id=7,
        user_message=run.message,
        locale="nl-NL",
        interaction_mode="READ",
        subject_scopes=["strategy", "bot"],
        required_domains=["plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-read-1",
        snapshot_id="snapshot-read-1",
        validation_id="validation-read-1",
        policy_decision_id="policy-read-1",
        evidence_set_hash="hash-read",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="309",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"strategy_id": 309, "setup_id": 293, "symbol": "BTC"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"bot_id": 170, "strategy_id": 309, "symbol": "BTC", "is_live": False},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="stale",
                confidence="medium",
                facts={"bot_id": 170, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[
            ReasoningDomainStatus(domain="plan_context", status="available", confidence="high"),
            ReasoningDomainStatus(domain="automation_context", status="degraded", confidence="medium", issue_codes=["bot_status_stale"]),
        ],
        policy=ReasoningPolicyContext(
            policy_class="read",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        allowed_response_modes=["READ", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=["bot_status_stale"],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-read-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    persisted = {}

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"error": "incomplete_structured_response"},
    )

    result = asyncio.run(service.reason(user_id=7, run_id="run-read-1", trace_id="trace-read-1"))

    assert result["status"] == "ready"
    assert result["mode"] == "READ"
    assert "Bot 170" in result["result"].direct_answer
    assert set(result["result"].evidence_refs_used) == {"E1", "E2", "E3"}


def test_reasoning_marks_grounded_read_fallback_ready_when_ai_rate_limited(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-read-rate-limit-1",
        user_id=7,
        message="Welke bot is aan mijn BTC-strategie gekoppeld, en staat deze bot momenteel live?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "BTC"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-read-rate-limit-1",
        run_id="run-read-rate-limit-1",
        user_id=7,
        interaction_mode="READ",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["strategy", "bot"],
        required_domains_json=["plan_context", "automation_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-read-rate-limit-1", "interaction_mode": "READ", "max_tool_calls": 15},
        snapshot_id="snapshot-read-rate-limit-1",
        validation_id="validation-read-rate-limit-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-read-rate-limit-1", snapshot_id="snapshot-read-rate-limit-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-read-rate-limit-1", validation_id="validation-read-rate-limit-1", integrity_status="valid", evidence_set_hash="hash-read-rate-limit", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-read-rate-limit-1",
                "run_id": "run-read-rate-limit-1",
                "user_id": 7,
                "policy_class": "read",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
                "shadow_safe": True,
                "created_at": "2026-08-20T10:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-read-rate-limit-1",
        user_id=7,
        user_message=run.message,
        locale="nl-NL",
        interaction_mode="READ",
        subject_scopes=["strategy", "bot"],
        required_domains=["plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-read-rate-limit-1",
        snapshot_id="snapshot-read-rate-limit-1",
        validation_id="validation-read-rate-limit-1",
        policy_decision_id="policy-read-rate-limit-1",
        evidence_set_hash="hash-read-rate-limit",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="309",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"strategy_id": 309, "setup_id": 293, "symbol": "BTC"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"bot_id": 170, "strategy_id": 309, "symbol": "BTC", "is_live": False},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="stale",
                confidence="medium",
                facts={"bot_id": 170, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[
            ReasoningDomainStatus(domain="plan_context", status="available", confidence="high"),
            ReasoningDomainStatus(domain="automation_context", status="degraded", confidence="medium", issue_codes=["bot_status_stale"]),
        ],
        policy=ReasoningPolicyContext(
            policy_class="read",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        allowed_response_modes=["READ", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=["bot_status_stale"],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-read-rate-limit-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    persisted = {}

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"error": "ai_rate_limited"},
    )

    result = asyncio.run(service.reason(user_id=7, run_id="run-read-rate-limit-1", trace_id="trace-read-rate-limit-1"))

    assert result["status"] == "ready"
    assert result["mode"] == "READ"
    assert persisted["status"] == "ready"
    assert "Bot 170" in result["result"].direct_answer


def test_reasoning_prefers_active_plan_fallback_over_generic_bot_read(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-read-plan-1",
        user_id=7,
        message="Wat is mijn actieve plan en welke bot is daaraan gekoppeld?",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "BTC"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-read-plan-1",
        run_id="run-read-plan-1",
        user_id=7,
        interaction_mode="READ",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["strategy", "bot"],
        required_domains_json=["plan_context", "automation_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-read-plan-1", "interaction_mode": "READ", "max_tool_calls": 15},
        snapshot_id="snapshot-read-plan-1",
        validation_id="validation-read-plan-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-read-plan-1", snapshot_id="snapshot-read-plan-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-read-plan-1", validation_id="validation-read-plan-1", integrity_status="valid", evidence_set_hash="hash-read-plan", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-read-plan-1",
                "run_id": "run-read-plan-1",
                "user_id": 7,
                "policy_class": "read",
                "allowed": True,
                "proposal_allowed": False,
                "confirmation_required": False,
                "step_up_required": False,
                "execution_allowed": False,
                "shadow_safe": True,
                "created_at": "2026-08-18T10:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-read-plan-1",
        user_id=7,
        user_message=run.message,
        locale="nl-NL",
        interaction_mode="READ",
        subject_scopes=["strategy", "bot"],
        required_domains=["plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-read-plan-1",
        snapshot_id="snapshot-read-plan-1",
        validation_id="validation-read-plan-1",
        policy_decision_id="policy-read-plan-1",
        evidence_set_hash="hash-read-plan",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_active_setup",
                domain="plan_context",
                entity_type="setup",
                entity_id="293",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"setup_id": 293, "name": "BTC Swing 4H Setup", "symbol": "BTC", "timeframe": "4H"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="309",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"strategy_id": 309, "setup_id": 293, "symbol": "BTC"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"bot_id": 170, "strategy_id": 309, "symbol": "BTC", "is_live": False},
            ),
            ReasoningEvidenceItem(
                evidence_id="E4",
                artifact_id="a4",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="stale",
                confidence="medium",
                facts={"bot_id": 170, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[
            ReasoningDomainStatus(domain="plan_context", status="available", confidence="high"),
            ReasoningDomainStatus(domain="automation_context", status="degraded", confidence="medium", issue_codes=["bot_status_stale"]),
        ],
        policy=ReasoningPolicyContext(
            policy_class="read",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
        ),
        allowed_response_modes=["READ", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=["bot_status_stale"],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-read-plan-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    service._persist_record = lambda **kwargs: asyncio.sleep(0, result=kwargs)
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"error": "incomplete_structured_response"},
    )

    result = asyncio.run(service.reason(user_id=7, run_id="run-read-plan-1", trace_id="trace-read-plan-1"))

    assert result["status"] == "ready"
    assert result["mode"] == "READ"
    assert "Je actieve plan voor BTC bestaat uit setup 293, strategie 309 en bot 170." == result["result"].direct_answer
    assert "Setup 293 (BTC Swing 4H Setup) gebruikt timeframe 4H" in result["result"].main_observation
    assert set(result["result"].evidence_refs_used) == {"E1", "E2", "E3", "E4"}


def test_reasoning_uses_grounded_watchlist_proposal_fallback_on_incomplete_structured_response(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-watch-1",
        user_id=7,
        message="Voeg ETH toe aan mijn watchlist.",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "ETH"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-watch-1",
        run_id="run-watch-1",
        user_id=7,
        interaction_mode="ACTION_PROPOSAL",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["watchlist"],
        required_domains_json=["identity_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-watch-1", "interaction_mode": "ACTION_PROPOSAL", "max_tool_calls": 15},
        snapshot_id="snapshot-watch-1",
        validation_id="validation-watch-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-watch-1", snapshot_id="snapshot-watch-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-watch-1", validation_id="validation-watch-1", integrity_status="valid", evidence_set_hash="hash-watch", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-watch-1",
                "run_id": "run-watch-1",
                "user_id": 7,
                "policy_class": "proposal",
                "allowed": True,
                "proposal_allowed": True,
                "confirmation_required": True,
                "step_up_required": False,
                "execution_allowed": False,
                "operation_type": "watchlist_add",
                "proposal_input_required": True,
                "shadow_safe": True,
                "created_at": "2026-08-18T10:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-watch-1",
        user_id=7,
        user_message=run.message,
        locale="nl-NL",
        interaction_mode="ACTION_PROPOSAL",
        subject_scopes=["watchlist"],
        required_domains=["identity_context"],
        orchestrator_result_id="orchestrator-watch-1",
        snapshot_id="snapshot-watch-1",
        validation_id="validation-watch-1",
        policy_decision_id="policy-watch-1",
        evidence_set_hash="hash-watch",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_active_asset",
                domain="identity_context",
                entity_type="asset",
                entity_id="ETH",
                asset="ETH",
                source="internal",
                freshness="unknown",
                confidence="high",
                facts={"symbol": "ETH", "asset_class": "crypto"},
            ),
        ],
        domain_statuses=[ReasoningDomainStatus(domain="identity_context", status="available", confidence="high")],
        policy=ReasoningPolicyContext(
            policy_class="proposal",
            allowed=True,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=False,
            execution_allowed=False,
            operation_type="watchlist_add",
            proposal_input_required=True,
        ),
        allowed_response_modes=["ACTION_PROPOSAL", "UNAVAILABLE"],
        allowed_operation_types=["watchlist_add"],
        uncertainty_codes=[],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-watch-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    persisted = {}

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(service.flags, "reasoning_max_retries", lambda: 0)
    monkeypatch.setattr(service.flags, "reasoning_timeout_seconds", lambda: 5)
    monkeypatch.setattr(service.flags, "reasoning_max_output_tokens", lambda: 600)
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_openai_runtime_status", lambda: {"configured": True})
    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.get_ai_availability", lambda: {"available": True})
    monkeypatch.setattr(
        "backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response",
        lambda **_kwargs: {"error": "incomplete_structured_response"},
    )

    result = asyncio.run(service.reason(user_id=7, run_id="run-watch-1", trace_id="trace-watch-1"))

    assert result["status"] == "failed"
    assert result["mode"] == "ACTION_PROPOSAL"
    assert result["result"].proposal_candidate is not None
    assert result["result"].proposal_candidate.operation_type == "watchlist_add"
    assert result["result"].proposal_candidate.proposed_changes["asset"] == "ETH"


def test_grounded_evaluation_fallback_prefers_strategy_fit_over_missing_indicators():
    fallback = FinnV2ReasoningFallbackService()
    context = ReasoningContextPackage(
        run_id="run-a2",
        user_id=7,
        user_message="Past mijn huidige BTC-strategie bij mijn risicoprofiel en tradingstijl?",
        locale="nl-NL",
        interaction_mode="EVALUATE",
        subject_scopes=["profile", "strategy"],
        required_domains=["identity_context", "plan_context"],
        orchestrator_result_id="orchestrator-a2",
        snapshot_id="snapshot-a2",
        validation_id="validation-a2",
        policy_decision_id="policy-a2",
        evidence_set_hash="hash-a2",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_profile",
                domain="identity_context",
                entity_type="profile",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"has_profile": True, "trader_profile": {"risk_profile": "balanced"}},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_indicator_configuration",
                domain="market_context",
                entity_type="indicator_configuration",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "BTC", "configured_indicators": []},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="309",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"strategy_id": 309, "setup_id": 293, "symbol": "BTC", "execution_mode": "fixed", "risk_profile": "balanced"},
            ),
        ],
        domain_statuses=[],
        policy=ReasoningPolicyContext(
            policy_class="advice",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
            operation_type=None,
            proposal_input_required=False,
        ),
        allowed_response_modes=["EVALUATE", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=[],
    )

    result = fallback.grounded_evaluation_draft(
        run_id="run-a2",
        user_id=7,
        context=context,
        model="gpt-test",
        error_codes=["provider_error"],
    )

    assert result.mode == "EVALUATE"
    assert "Strategie 309" in result.direct_answer
    assert "indicatorconfiguratie" not in result.direct_answer.lower()


def test_grounded_evaluation_fallback_answers_strategy_entry_question_before_indicator_gap():
    fallback = FinnV2ReasoningFallbackService()
    context = ReasoningContextPackage(
        run_id="run-b2",
        user_id=7,
        user_message="Welke belangrijkste entryvoorwaarde uit mijn BTC-strategie moet bevestigd zijn voordat mijn plan een entry toestaat?",
        locale="nl-NL",
        interaction_mode="EVALUATE",
        subject_scopes=["strategy"],
        required_domains=["plan_context"],
        orchestrator_result_id="orchestrator-b2",
        snapshot_id="snapshot-b2",
        validation_id="validation-b2",
        policy_decision_id="policy-b2",
        evidence_set_hash="hash-b2",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="309",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"strategy_id": 309, "setup_id": 293, "symbol": "BTC", "entry": "62000", "entry_type": "limit"},
            ),
        ],
        domain_statuses=[],
        policy=ReasoningPolicyContext(
            policy_class="advice",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
            operation_type=None,
            proposal_input_required=False,
        ),
        allowed_response_modes=["EVALUATE", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=[],
    )

    result = fallback.grounded_evaluation_draft(
        run_id="run-b2",
        user_id=7,
        context=context,
        model="gpt-test",
        error_codes=["provider_error"],
    )

    assert "entryvoorwaarde" in result.direct_answer.lower()
    assert "62000" in result.direct_answer


def test_grounded_evaluation_fallback_uses_plan_specific_details_when_indicators_missing():
    fallback = FinnV2ReasoningFallbackService()
    btc_context = ReasoningContextPackage(
        run_id="run-g5-btc",
        user_id=7,
        user_message="Bekijk mijn profiel, indicatoren, setup, strategie en gekoppelde bot.",
        locale="nl-NL",
        interaction_mode="EVALUATE",
        subject_scopes=["profile", "indicators", "setup", "strategy", "bot"],
        required_domains=["identity_context", "market_context", "plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-g5-btc",
        snapshot_id="snapshot-g5-btc",
        validation_id="validation-g5-btc",
        policy_decision_id="policy-g5-btc",
        evidence_set_hash="hash-g5-btc",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_profile",
                domain="identity_context",
                entity_type="profile",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"has_profile": False, "trader_profile": {}},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_indicator_configuration",
                domain="market_context",
                entity_type="indicator_configuration",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"symbol": "BTC", "configured_indicators": []},
            ),
            ReasoningEvidenceItem(
                evidence_id="E3",
                artifact_id="a3",
                tool_name="read_active_setup",
                domain="plan_context",
                entity_type="setup",
                entity_id="295",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"setup_id": 295, "symbol": "BTC", "name": "BTC Swing 4H Gate Setup", "timeframe": "4H"},
            ),
            ReasoningEvidenceItem(
                evidence_id="E4",
                artifact_id="a4",
                tool_name="read_linked_strategy",
                domain="plan_context",
                entity_type="strategy",
                entity_id="311",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={
                    "strategy_id": 311,
                    "setup_id": 295,
                    "symbol": "BTC",
                    "execution_mode": "fixed",
                    "entry": "68000",
                    "stop_loss": "64000",
                    "targets": ["76000", "82000"],
                },
            ),
            ReasoningEvidenceItem(
                evidence_id="E5",
                artifact_id="a5",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="172",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"bot_id": 172, "strategy_id": 311, "is_live": False, "is_active": True},
            ),
            ReasoningEvidenceItem(
                evidence_id="E6",
                artifact_id="a6",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="172",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"bot_id": 172, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[],
        policy=ReasoningPolicyContext(
            policy_class="advice",
            allowed=True,
            proposal_allowed=False,
            confirmation_required=False,
            step_up_required=False,
            execution_allowed=False,
            operation_type=None,
            proposal_input_required=False,
        ),
        allowed_response_modes=["EVALUATE", "UNAVAILABLE"],
        allowed_operation_types=[],
        uncertainty_codes=[],
    )
    aapl_context = btc_context.copy(deep=True)
    aapl_context.run_id = "run-g5-aapl"
    aapl_context.evidence_set_hash = "hash-g5-aapl"
    aapl_context.evidence[1].asset = "AAPL"
    aapl_context.evidence[1].facts = {"symbol": "AAPL", "configured_indicators": []}
    aapl_context.evidence[2].entity_id = "296"
    aapl_context.evidence[2].asset = "AAPL"
    aapl_context.evidence[2].facts = {"setup_id": 296, "symbol": "AAPL", "name": "AAPL Swing 1D Gate Setup", "timeframe": "1D"}
    aapl_context.evidence[3].entity_id = "312"
    aapl_context.evidence[3].asset = "AAPL"
    aapl_context.evidence[3].facts = {
        "strategy_id": 312,
        "setup_id": 296,
        "symbol": "AAPL",
        "execution_mode": "fixed",
        "entry": "220",
        "stop_loss": "205",
        "targets": ["245", "260"],
    }
    aapl_context.evidence[4].entity_id = "173"
    aapl_context.evidence[4].asset = "AAPL"
    aapl_context.evidence[4].facts = {"bot_id": 173, "strategy_id": 312, "is_live": False, "is_active": True}
    aapl_context.evidence[5].entity_id = "173"
    aapl_context.evidence[5].asset = "AAPL"
    aapl_context.evidence[5].facts = {"bot_id": 173, "is_live": False, "is_active": True}

    btc_result = fallback.grounded_evaluation_draft(
        run_id="run-g5-btc",
        user_id=7,
        context=btc_context,
        model="gpt-test",
        error_codes=["ai_rate_limited"],
    )
    aapl_result = fallback.grounded_evaluation_draft(
        run_id="run-g5-aapl",
        user_id=7,
        context=aapl_context,
        model="gpt-test",
        error_codes=["ai_rate_limited"],
    )

    assert "4H" in btc_result.direct_answer
    assert "68000" in btc_result.main_observation
    assert "76000" in btc_result.main_observation
    assert "1D" in aapl_result.direct_answer
    assert "220" in aapl_result.main_observation
    assert "245" in aapl_result.main_observation
    assert btc_result.direct_answer != aapl_result.direct_answer
    assert btc_result.main_observation != aapl_result.main_observation


def test_reasoning_short_circuits_blocked_live_bot_activation_before_provider(monkeypatch):
    service = FinnV2ReasoningService(session=object())
    run = SimpleNamespace(
        id="run-live-bot-1",
        user_id=7,
        message="Activeer deze bot live.",
        visibility="visible",
        feature_mode="visible_runtime",
        client_context_json={},
        workspace_hints_json={"asset": "BTC"},
    )
    orchestrator_row = SimpleNamespace(
        id="orchestrator-live-bot-1",
        run_id="run-live-bot-1",
        user_id=7,
        interaction_mode="ACTION_PROPOSAL",
        analysis_version="2026-08-17.block4",
        subject_scopes_json=["bot"],
        required_domains_json=["plan_context", "automation_context"],
        optional_domains_json=[],
        tool_plan_json={"run_id": "run-live-bot-1", "interaction_mode": "ACTION_PROPOSAL", "max_tool_calls": 15},
        snapshot_id="snapshot-live-bot-1",
        validation_id="validation-live-bot-1",
        outcome="reasoning_ready",
        selected_clarification_json=None,
        unavailable_codes_json=[],
        uncertainty_codes_json=[],
        orchestrator_version="2026-08-17.block4",
        created_at=datetime.now(timezone.utc),
    )
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=run)
    service.orchestrators.get_for_run_version = lambda **_kwargs: asyncio.sleep(0, result=orchestrator_row)
    service.snapshots.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="snapshot-live-bot-1", snapshot_id="snapshot-live-bot-1"))
    service.validations.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(id="validation-live-bot-1", validation_id="validation-live-bot-1", integrity_status="valid", evidence_set_hash="hash-live-bot", domains=[]))
    service.policies.get_for_run_version = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            decision_json={
                "policy_decision_id": "policy-live-bot-1",
                "run_id": "run-live-bot-1",
                "user_id": 7,
                "policy_class": "high_risk_action",
                "allowed": False,
                "proposal_allowed": True,
                "confirmation_required": True,
                "step_up_required": True,
                "execution_allowed": False,
                "operation_type": "activate_live_bot",
                "proposal_input_required": True,
                "blocking_codes": ["live_action_disabled"],
                "shadow_safe": True,
                "created_at": "2026-08-19T05:00:00+00:00",
            }
        ),
    )
    context = ReasoningContextPackage(
        run_id="run-live-bot-1",
        user_id=7,
        user_message=run.message,
        locale="nl-NL",
        interaction_mode="ACTION_PROPOSAL",
        subject_scopes=["bot"],
        required_domains=["plan_context", "automation_context"],
        orchestrator_result_id="orchestrator-live-bot-1",
        snapshot_id="snapshot-live-bot-1",
        validation_id="validation-live-bot-1",
        policy_decision_id="policy-live-bot-1",
        evidence_set_hash="hash-live-bot",
        evidence=[
            ReasoningEvidenceItem(
                evidence_id="E1",
                artifact_id="a1",
                tool_name="read_linked_bot",
                domain="automation_context",
                entity_type="bot",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"bot_id": 170, "strategy_id": 309, "is_live": False},
            ),
            ReasoningEvidenceItem(
                evidence_id="E2",
                artifact_id="a2",
                tool_name="read_bot_status",
                domain="automation_context",
                entity_type="bot_status",
                entity_id="170",
                asset="BTC",
                source="internal",
                freshness="fresh",
                confidence="high",
                facts={"bot_id": 170, "is_live": False, "is_active": True},
            ),
        ],
        domain_statuses=[],
        policy=ReasoningPolicyContext(
            policy_class="high_risk_action",
            allowed=False,
            proposal_allowed=True,
            confirmation_required=True,
            step_up_required=True,
            execution_allowed=False,
            operation_type="activate_live_bot",
            proposal_input_required=True,
            blocking_codes=["live_action_disabled"],
        ),
        allowed_response_modes=["UNAVAILABLE"],
        allowed_operation_types=["activate_live_bot"],
        uncertainty_codes=[],
    )
    service.contexts.build = lambda **_kwargs: asyncio.sleep(0, result=context)
    service.contexts.input_hash = lambda *_args, **_kwargs: "hash-live-bot-input"
    service.reasoning.get_reusable_result = lambda **_kwargs: asyncio.sleep(0, result=None)
    service.traces.append_event = lambda **_kwargs: asyncio.sleep(0, result=None)
    persisted = {}

    async def _persist_record(**kwargs):
        persisted.update(kwargs)
        return kwargs

    service._persist_record = _persist_record
    monkeypatch.setattr(service, "_resolved_model", lambda: "gpt-test")

    def _fail_if_called(**_kwargs):
        raise AssertionError("provider_call_should_not_happen")

    monkeypatch.setattr("backend.services.finn_v2_reasoning_service.openai_client.ask_gpt_structured_response", _fail_if_called)

    result = asyncio.run(service.reason(user_id=7, run_id="run-live-bot-1", trace_id="trace-live-bot-1"))

    assert result["status"] == "unavailable"
    assert result["mode"] == "UNAVAILABLE"
    assert "niet live activeren" in result["result"].direct_answer.lower()
