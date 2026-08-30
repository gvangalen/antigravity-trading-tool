import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_domain_validation_schema import EvidenceValidationResult
from backend.schemas.finn_v2_orchestrator_schema import OrchestratorResult
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_response_verifier_service import FinnV2VerifierRejected
from backend.schemas.finn_v2_verifier_schema import CoverageVerification, VerifierResult


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


class _FakeConversationRepo:
    def __init__(self, context=None):
        self.context = context or {}
        self.updated = None

    async def get_context(self, **_kwargs):
        return dict(self.context)

    async def update_context(self, **kwargs):
        self.updated = kwargs


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
                    {"domain": "identity_context", "status": "available", "confidence": "high"},
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
    service = FinnV2OrchestratorService(session=object())
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
                    {"domain": "identity_context", "status": "available", "confidence": "high"},
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


def test_orchestrator_persists_only_verified_conversation_references():
    run = SimpleNamespace(
        id="run-conversation-1",
        user_id=7,
        trace_id="trace-conversation-1",
        conversation_id="conversation-1",
        status="planned",
        visibility="visible",
        feature_mode="visible_readonly",
        message="Welke setup gebruik ik voor BTC?",
        workspace_hints_json={},
        client_context_json={},
    )
    service = FinnV2OrchestratorService(session=object())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()
    service.results = _FakeResultRepo()
    service.conversations = _FakeConversationRepo({"last_mode": "READ"})
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_state_assembly_enabled = lambda: True
    service.flags.should_run_block5_shadow = lambda _user_id: False
    service.flags.should_run_block6_shadow = lambda _user_id: False
    service.flags.should_run_block7_shadow = lambda _user_id: False

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-conversation-1",
                "snapshot_id": "snapshot-conversation-1",
                "run_id": run.id,
                "user_id": run.user_id,
                "evidence_set_hash": "hash-conversation-1",
                "integrity_status": "valid",
                "domains": [
                    {"domain": "identity_context", "status": "available", "confidence": "high"},
                    {"domain": "plan_context", "status": "available", "confidence": "high"},
                ],
                "issues": [],
                "validated_at": "2026-08-17T10:00:00+00:00",
            }
        )
        return SimpleNamespace(snapshot_id="snapshot-conversation-1"), validation

    service.tools.execute_tool_plan = lambda **_kwargs: asyncio.sleep(0, result=[])
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(policy_class="read", allowed=True, proposal_input_required=False, blocking_codes=[]))
    service.policy.persist = lambda *_args, **_kwargs: asyncio.sleep(0)
    service.reasoning.reason = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(status="completed"))
    service.verifier.verify_run = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            mode="READ",
            verifier_status="passed",
            main_observation="The BTC setup is active.",
            evidence_refs_used=["evidence-setup-1"],
            proposal_id=None,
        ),
    )

    asyncio.run(service.execute_run(run_id=run.id, user_id=run.user_id, trace_id=run.trace_id))

    assert service.conversations.updated["conversation_id"] == "conversation-1"
    context = service.conversations.updated["context"]
    assert context["conversation_state_version"] == "finn_v2.conversation-contracts.v1"
    assert context["last_mode"] == "READ"
    assert context["last_user_goal"] == "read_setup"
    assert context["resolved_asset"] == "BTC"
    assert context["last_evidence_refs"] == ["evidence-setup-1"]
    assert context["last_verified_conclusion"] == "The BTC setup is active."
    assert context["last_primary_domains"] == ["setup"]
    assert context["last_required_information_scopes"] == ["active_asset", "active_setup"]
    assert context["last_verified_context"] == {
        "operation_id": "read_active_setup",
        "contract_version": "2026-08-23.operation-contracts.v1",
        "mode": "READ",
        "conclusion": "The BTC setup is active.",
        "evidence_refs": ["evidence-setup-1"],
        "required_scopes": ["active_asset", "active_setup"],
        "resolved_entities": {"asset": "BTC"},
    }


def test_unavailable_delivery_records_diagnostics_without_overwriting_verified_context():
    service = FinnV2OrchestratorService(session=object())
    service.conversations = _FakeConversationRepo()
    previous = {
        "last_verified_context": {
            "verified_response_id": "verified-previous",
            "operation_id": "read_active_setup",
            "mode": "READ",
            "conclusion": "BTC uses the saved 4H setup.",
            "evidence_refs": ["evidence-previous"],
            "resolved_entities": {"asset": "BTC", "setup_id": 309},
        }
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            explicit_asset=None,
            explicit_setup_id=None,
            explicit_strategy_id=None,
            explicit_bot_id=None,
            interaction_mode="UNAVAILABLE",
            request_plan=SimpleNamespace(operation_id="unavailable", operation_contract_version="contract-v1", operation_state={}),
        ),
        tool_plan=SimpleNamespace(entity_selectors={}),
    )
    response = SimpleNamespace(
        verifier_status="passed",
        mode="UNAVAILABLE",
        uncertainty_codes=["insufficient_context"],
    )

    asyncio.run(
        service._update_conversation_context(
            conversation_id="conversation-1",
            user_id=7,
            existing_context=previous,
            result=result,
            verified_response=response,
        )
    )

    context = service.conversations.updated["context"]
    assert context["last_verified_context"] == previous["last_verified_context"]
    assert context["last_turn_diagnostics"] == {
        "operation_id": "unavailable",
        "mode": "UNAVAILABLE",
        "verifier_status": "passed",
        "reason_codes": ["insufficient_context"],
    }


def test_downgraded_evaluate_retains_only_evidence_lineage_for_safe_followups():
    service = FinnV2OrchestratorService(session=object())
    service.conversations = _FakeConversationRepo()
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            explicit_asset="BTC", explicit_setup_id=293, explicit_strategy_id=309,
            explicit_bot_id=170, interaction_mode="EVALUATE",
            request_plan=SimpleNamespace(operation_id="evaluate_plan", operation_contract_version="contract-v1", operation_state={}),
        ),
        tool_plan=SimpleNamespace(entity_selectors={"asset": "BTC"}),
    )
    response = SimpleNamespace(
        verifier_status="downgraded", mode="EVALUATE", run_id="run-degraded",
        evidence_refs_used=["E1", "E2"], uncertainty_codes=["response_field_incomplete"],
    )

    asyncio.run(service._update_conversation_context(
        conversation_id="conversation-1", user_id=7, existing_context={}, result=result, verified_response=response,
    ))

    degraded = service.conversations.updated["context"]["last_degraded_context"]
    assert degraded["evidence_refs"] == ["E1", "E2"]
    assert degraded["resolved_entities"] == {"asset": "BTC", "setup_id": 293, "strategy_id": 309, "bot_id": 170}
    assert degraded["financial_conclusion_verified"] is False
    assert degraded["terminal_status"] == "downgraded"
    assert degraded["evidence_scopes"] == []
    assert {section["kind"] for section in degraded["released_response_sections"]} == {
        "verification_limitation", "evidence_availability",
    }
    assert "conclusion" not in degraded and "response" not in degraded


def test_canonical_context_does_not_promote_generic_bot_text_without_lineage_proof():
    service = FinnV2OrchestratorService(session=object())
    service.conversations = _FakeConversationRepo()
    existing = {
        "conversation_state_version": "finn_v2.conversation-contracts.v1",
        "last_verified_context": {"verified_response_id": "verified-prior", "resolved_entities": {"asset": "BTC"}},
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            explicit_asset="BTC", explicit_setup_id=None, explicit_strategy_id=None, explicit_bot_id=170,
            interaction_mode="EVALUATE", request_plan=SimpleNamespace(operation_id="evaluate_bot", operation_contract_version="v1", operation_state={}),
        ),
        tool_plan=SimpleNamespace(entity_selectors={"asset": "BTC", "bot_id": 170}),
    )
    response = SimpleNamespace(
        verifier_status="passed", mode="EVALUATE", run_id="run-generic", evidence_refs_used=["E1"],
        main_observation="Plancontext is beschikbaar.", direct_answer="Plancontext is beschikbaar.",
        reasoning_provenance={"lineage_eligible": False}, uncertainty_codes=[],
    )

    asyncio.run(service._update_conversation_context(
        conversation_id="conversation-1", user_id=7, existing_context=existing, result=result, verified_response=response,
    ))

    assert service.conversations.updated["context"]["last_verified_context"] == existing["last_verified_context"]


def test_verified_proposal_preserves_financial_lineage_and_marks_guided_state_proposed():
    service = FinnV2OrchestratorService(session=object())
    service.conversations = _FakeConversationRepo()
    previous = {
        "last_verified_context": {
            "verified_response_id": "verified-plan",
            "operation_id": "evaluate_plan",
            "mode": "EVALUATE",
            "conclusion": "BTC needs a testable entry rule.",
            "evidence_refs": ["E1"],
            "resolved_entities": {"asset": "BTC"},
        }
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            explicit_asset="BTC", explicit_setup_id=None,
            explicit_strategy_id=None, explicit_bot_id=None,
            interaction_mode="CREATE_PROPOSAL",
            request_plan=SimpleNamespace(
                operation_id="create_setup",
                operation_contract_version="contract-v1",
                operation_state={
                    "operation_id": "create_setup",
                    "contract_version": "contract-v1",
                    "collected_inputs": {
                        "symbol": "BTC", "setup_type": "trade",
                        "timeframe": "4H", "name": "BTC QA",
                    },
                    "missing_required_inputs": [],
                },
                required_information_scopes=["active_asset"],
            ),
        ),
        tool_plan=SimpleNamespace(entity_selectors={"asset": "BTC"}),
    )
    response = SimpleNamespace(
        verifier_status="passed", mode="CREATE_PROPOSAL",
        proposal_id="proposal-setup", uncertainty_codes=[],
        evidence_refs_used=["Easset"],
    )

    asyncio.run(service._update_conversation_context(
        conversation_id="conversation-1", user_id=7,
        existing_context=previous, result=result, verified_response=response,
    ))

    context = service.conversations.updated["context"]
    assert context["last_verified_context"] == previous["last_verified_context"]
    assert context["active_guided_operation"]["status"] == "proposed"
    assert context["active_guided_operation"]["open_proposal_id"] == "proposal-setup"


def test_cancelled_guided_operation_is_removed_without_erasing_verified_context():
    service = FinnV2OrchestratorService(session=object())
    service.conversations = _FakeConversationRepo()
    previous = {
        "last_verified_context": {
            "verified_response_id": "verified-previous",
            "operation_id": "read_active_setup",
            "mode": "READ",
            "conclusion": "BTC uses the saved 4H setup.",
            "evidence_refs": ["evidence-previous"],
            "resolved_entities": {"asset": "BTC", "setup_id": 309},
        },
        "active_guided_operation": {
            "operation_id": "create_setup",
            "contract_version": "2026-08-23.operation-contracts.v1",
            "collected_inputs": {"symbol": "BTC", "setup_type": "trade"},
            "missing_required_inputs": ["name"],
        },
    }
    result = SimpleNamespace(
        analysis=SimpleNamespace(
            explicit_asset=None,
            explicit_setup_id=None,
            explicit_strategy_id=None,
            explicit_bot_id=None,
            interaction_mode="CLARIFICATION",
            request_plan=SimpleNamespace(
                operation_id="clarify_request",
                operation_contract_version="contract-v1",
                operation_state={
                    "operation_id": "create_setup",
                    "status": "cancelled",
                },
            ),
        ),
        tool_plan=SimpleNamespace(entity_selectors={}),
    )
    response = SimpleNamespace(
        verifier_status="passed",
        mode="CLARIFICATION",
        uncertainty_codes=[],
    )

    asyncio.run(
        service._update_conversation_context(
            conversation_id="conversation-1",
            user_id=7,
            existing_context=previous,
            result=result,
            verified_response=response,
        )
    )

    context = service.conversations.updated["context"]
    assert context["last_verified_context"] == previous["last_verified_context"]
    assert "active_guided_operation" not in context
    assert "operation_state" not in context
    assert context["last_turn_diagnostics"]["reason_codes"] == ["guided_operation_cancelled"]


def test_orchestrator_classifies_requested_operation_for_action_proposal_modes():
    run = SimpleNamespace(
        id="run-3",
        user_id=7,
        trace_id="trace-3",
        status="planned",
        visibility="visible",
        feature_mode="visible_readonly",
        message="Voeg ETH toe aan mijn watchlist.",
        workspace_hints_json={},
        client_context_json={},
    )
    service = FinnV2OrchestratorService(session=object())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()
    service.results = _FakeResultRepo()
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_state_assembly_enabled = lambda: True
    service.flags.should_run_block5_shadow = lambda _user_id: False
    service.flags.should_run_block6_shadow = lambda _user_id: False
    service.flags.should_run_block7_shadow = lambda _user_id: False
    analyzed = service.analysis.analyze(message=run.message)
    analyzed.interaction_mode = "ACTION_PROPOSAL"
    analyzed.subject_scopes = ["watchlist"]
    analyzed.requests_change = True
    analyzed.requests_execution = False
    analyzed.reasoning_required = True
    service.analysis.analyze = lambda **_kwargs: analyzed

    async def _execute_tool_plan(**kwargs):
        return []

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-3",
                "snapshot_id": "snapshot-3",
                "run_id": "run-3",
                "user_id": 7,
                "evidence_set_hash": "hash-3",
                "integrity_status": "valid",
                "domains": [
                    {"domain": "identity_context", "status": "available", "confidence": "high"},
                    {"domain": "market_context", "status": "available", "confidence": "high"},
                ],
                "issues": [],
                "validated_at": "2026-08-18T10:00:00+00:00",
            }
        )
        return SimpleNamespace(id="snapshot-3", snapshot_id="snapshot-3", user_id=7), validation

    captured = {}

    async def _evaluate_run(**kwargs):
        captured["requested_operation"] = kwargs["requested_operation"]
        return SimpleNamespace(
            policy_class="proposal",
            allowed=True,
            proposal_input_required=True,
            blocking_codes=[],
        )

    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = _evaluate_run
    service.policy.persist = lambda *args, **kwargs: asyncio.sleep(0, result=None)
    service.reasoning.reason = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(status="ready"))
    service.verifier.verify_run = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(mode="ACTION_PROPOSAL", verifier_status="passed"))
    service.risk.classify_requested_operation = lambda **_kwargs: "activate_paper_bot"

    asyncio.run(service.execute_run(run_id="run-3", user_id=7, trace_id="trace-3"))

    assert captured["requested_operation"] == "watchlist_add"


def test_orchestrator_terminalizes_a_persisted_verifier_reject_without_a_second_result():
    run = SimpleNamespace(
        id="run-rejected-1",
        user_id=7,
        trace_id="trace-rejected-1",
        status="planned",
        visibility="visible",
        feature_mode="visible_readonly",
        message="Bekijk mijn plan.",
        workspace_hints_json={},
        client_context_json={},
    )
    service = FinnV2OrchestratorService(session=object())
    service.runs = _FakeRunRepo(run)
    service.traces = _FakeTraceRepo()
    service.results = _FakeResultRepo()
    service.flags.is_tool_registry_enabled = lambda: True
    service.flags.is_state_assembly_enabled = lambda: True
    service.flags.should_run_block5_shadow = lambda _user_id: False
    service.flags.should_run_block6_shadow = lambda _user_id: False
    service.flags.should_run_block7_shadow = lambda _user_id: False

    async def _execute_tool_plan(**_kwargs):
        return []

    async def _run_state_pipeline(**_kwargs):
        validation = EvidenceValidationResult.parse_obj(
            {
                "validation_id": "validation-rejected-1",
                "snapshot_id": "snapshot-rejected-1",
                "run_id": run.id,
                "user_id": run.user_id,
                "evidence_set_hash": "hash-rejected-1",
                "integrity_status": "valid",
                "domains": [{"domain": "plan_context", "status": "available", "confidence": "high"}],
                "issues": [],
                "validated_at": "2026-08-17T10:00:00+00:00",
            }
        )
        return SimpleNamespace(snapshot_id="snapshot-rejected-1"), validation

    verifier = VerifierResult(
        verifier_result_id="verifier-rejected-1",
        run_id=run.id,
        user_id=run.user_id,
        draft_id="draft-rejected-1",
        passed=False,
        action="reject",
        claim_results=[],
        coverage=CoverageVerification(required_scopes=["profile"], covered_scopes=[], missing_scopes=["profile"], coverage_ok=False),
        schema_ok=True,
        ownership_ok=True,
        evidence_ok=False,
        relevance_ok=True,
        mode_purity_ok=True,
        uncertainty_ok=True,
        follow_up_ok=True,
        proposal_ok=True,
        policy_ok=True,
        safety_ok=True,
        reason_codes=["response_scope_incomplete"],
        semantic_verifier_used=False,
        created_at=datetime.now(timezone.utc),
    )
    service.tools.execute_tool_plan = _execute_tool_plan
    service.tools.run_state_pipeline = _run_state_pipeline
    service.policy.evaluate_run = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(policy_class="read", allowed=True, proposal_input_required=False, blocking_codes=[]))
    service.policy.persist = lambda *_args, **_kwargs: asyncio.sleep(0)
    service.reasoning.reason = lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(status="completed"))
    service.verifier.verify_run = lambda **_kwargs: asyncio.sleep(0, result=_raise_reject(verifier))

    result = asyncio.run(service.execute_run(run_id=run.id, user_id=run.user_id, trace_id=run.trace_id))

    assert result.run_id == run.id
    assert len(service.results.created) == 1
    assert service.consume_phase_outcome().terminal_status == "rejected"
    assert service.consume_phase_outcome().verifier_action == "reject"
    assert [event["event_type"] for event in service.traces.events][-1] == "orchestrator_rejected"


def _raise_reject(verifier):
    raise FinnV2VerifierRejected(verifier)


def test_orchestrator_commits_before_cross_session_phase_transition():
    state = {"committed": False, "transitions": []}

    class _Session:
        async def commit(self):
            state["committed"] = True

        async def rollback(self):
            raise AssertionError("rollback must not run for a successful boundary")

    async def _transition(**kwargs):
        assert state["committed"] is True
        state["transitions"].append(kwargs)

    service = FinnV2OrchestratorService(session=_Session(), phase_transition=_transition)

    asyncio.run(
        service._transition_phase(
            run_id="run-boundary-1",
            user_id=7,
            next_status="reasoning",
            interaction_mode="EVALUATE",
        )
    )

    assert state["transitions"] == [
        {
            "run_id": "run-boundary-1",
            "user_id": 7,
            "next_status": "reasoning",
            "interaction_mode": "EVALUATE",
            "response_source": "v2_runtime",
        }
    ]
