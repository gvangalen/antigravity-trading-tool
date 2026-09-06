from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.domain.finn_v2_runtime_contract import (
    RUNTIME_CONTRACT_VERSION,
    RuntimeContractConflictError,
    RuntimeContractImmutableFieldError,
    new_runtime_contract_state,
    record_initial_intent,
    record_selection,
    terminal_projection,
)
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.services.finn_v2_flag_service import FinnV2FlagService


ROOT = Path(__file__).resolve().parents[1]


def _run():
    return SimpleNamespace(
        id="run-contract-1",
        conversation_id="conversation-contract-1",
        trace_id="trace-contract-1",
        user_id=7,
        message="Beoordeel mijn BTC-plan.",
    )


def test_runtime_contract_identity_is_present_before_selector_and_intent_is_write_once():
    state = new_runtime_contract_state(run=_run(), contract_id="contract-run-contract-1")

    assert state["identity"] == {
        "run_id": "run-contract-1",
        "conversation_id": "conversation-contract-1",
        "trace_id": "trace-contract-1",
        "user_id": 7,
    }
    assert state["terminal_status"] == "pending"
    assert state["contract_version"] == RUNTIME_CONTRACT_VERSION

    selected = record_initial_intent(state, operation_id="evaluate_plan", requested_mode="EVALUATE")
    replay = record_initial_intent(selected, operation_id="evaluate_plan", requested_mode="EVALUATE")
    assert replay["initial_operation_id"] == "evaluate_plan"
    with pytest.raises(RuntimeContractImmutableFieldError):
        record_initial_intent(selected, operation_id="read_plan", requested_mode="READ")


def test_run_creation_exposes_only_safe_contract_identity_before_worker_execution():
    source = (ROOT / "api" / "finn_v2_api.py").read_text(encoding="utf-8")
    create_source = source.split("async def create_finn_v2_run(", 1)[1].split("@router.get", 1)[0]

    assert "db: AsyncSession = Depends(get_db)" in create_source
    assert "FinnV2RuntimeContractRepository(db).get_for_run(run_id=run_id)" in create_source
    assert '"contract_id": runtime_contract.contract_id' in create_source
    assert '"revision": runtime_contract.revision' in create_source
    assert "runtime_contract_missing_after_run_creation" in create_source


def test_runtime_repository_rejects_identity_mutation_and_replayed_initial_intent_is_not_a_transition():
    source = (ROOT / "infrastructure" / "repositories" / "finn_v2_runtime_contract_repository.py").read_text(encoding="utf-8")
    assert "must not create another state transition or revision" in source
    assert "runtime_contract_identity_is_immutable" in source
    assert "if current_state.get(\"initial_operation_id\") is not None:" in source


def test_follow_up_parent_contract_lookup_excludes_the_current_run():
    """A newly created child contract must never hide its conversation parent."""
    repository = (ROOT / "infrastructure" / "repositories" / "finn_v2_runtime_contract_repository.py").read_text(encoding="utf-8")
    orchestrator = (ROOT / "services" / "finn_v2_orchestrator_service.py").read_text(encoding="utf-8")

    assert "exclude_run_id" in repository
    assert "exclude_run_id=run_id" in orchestrator


def test_continuation_context_uses_the_persisted_parent_contract_state():
    """A short follow-up must receive released lineage and its active flow."""
    from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService

    expected_lineage = {
        "last_verified_context": {
            "operation_id": "evaluate_plan",
            "resolved_entities": {"asset": "ETH"},
            "response": "De planbeoordeling is vrijgegeven.",
            "evidence_refs": ["evidence-plan-1"],
        }
    }
    expected_flow = {
        "flow_id": "flow-setup-1",
        "operation_id": "create_setup",
        "target_asset": "ETH",
        "missing_required_inputs": ["timeframe"],
    }

    class _Conversations:
        async def get_context(self, **_kwargs):
            return {"legacy_projection": True, "last_verified_context": {"asset": "STALE"}}

    class _Contracts:
        async def get_latest_for_conversation(self, **kwargs):
            assert kwargs["exclude_run_id"] == "child-run"
            return SimpleNamespace(
                run_id="parent-run",
                state_json={"lineage_state": expected_lineage, "guided_state": expected_flow},
            )

    service = object.__new__(FinnV2OrchestratorService)
    service.conversations = _Conversations()
    service.runtime_contracts = _Contracts()

    context = asyncio.run(
        service._load_continuation_context(
            conversation_id="conversation-1",
            user_id=7,
            run_id="child-run",
        )
    )

    assert context["legacy_projection"] is True
    assert context["last_verified_context"] == expected_lineage["last_verified_context"]
    assert context["active_guided_operation"] == expected_flow


def test_persisted_parent_contract_content_reaches_the_structured_selector_input():
    """The selector receives released lineage content, not merely a parent id."""
    from backend.services.finn_v2_operation_classification_service import FinnV2OperationClassificationService
    from backend.services.finn_v2_structured_operation_selector_service import FinnV2StructuredOperationSelection

    captured = {}

    class _Selector:
        def select(self, **kwargs):
            captured.update(kwargs)
            return FinnV2StructuredOperationSelection(
                operation_id="explain_previous_evidence",
                confidence=0.9,
                entities={},
                target_asset=None,
                conversation_reference="previous_verified_response",
                missing_inputs=(),
                ambiguity_reason=None,
                semantic_frame={"goal": "explain", "object": "evidence", "reference_kind": "previous_verified_response"},
            ), None

    context = {
        "last_verified_context": {
            "verified_response_id": "verified-parent-1",
            "operation_id": "evaluate_plan",
            "resolved_entities": {"asset": "ETH"},
            "response": "De vrijgegeven planbeoordeling.",
            "evidence_refs": ["evidence-parent-1"],
        },
        "active_guided_operation": {
            "operation_id": "create_setup",
            "missing_required_inputs": ["name"],
        },
    }

    result = FinnV2OperationClassificationService(structured_selector=_Selector()).classify(
        message="Kun je de onderbouwing van die beoordeling toelichten?",
        conversation_context=context,
    )

    assert result.operation_id == "explain_previous_evidence"
    assert captured["verified_context"]["last_verified_context"] == context["last_verified_context"]
    assert captured["verified_context"]["active_guided_operation"] == context["active_guided_operation"]


def test_terminal_projection_uses_the_same_immutable_contract_identity():
    state = record_initial_intent(
        new_runtime_contract_state(run=_run(), contract_id="contract-run-contract-1"),
        operation_id="evaluate_plan",
        requested_mode="EVALUATE",
    )
    projection = terminal_projection(
        state,
        status="failed",
        mode="UNAVAILABLE",
        response={"mode": "UNAVAILABLE", "content": "Veilige foutrespons."},
        error_code="orchestrator_failed",
    )

    assert projection["contract_id"] == "contract-run-contract-1"
    assert projection["run_id"] == "run-contract-1"
    assert projection["initial_operation_id"] == "evaluate_plan"
    assert projection["terminal_status"] == "failed"
    assert projection["terminal_response_type"] == "failure"


def test_explicit_canonical_target_cannot_be_replaced_after_selection():
    state = record_initial_intent(
        new_runtime_contract_state(run=_run(), contract_id="contract-run-contract-1"),
        operation_id="evaluate_plan",
        requested_mode="EVALUATE",
    )
    selected = record_selection(
        state,
        canonical_target="ETH",
        target_source="explicit_current_turn",
        original_target_text="Ethereum",
        target_type="asset",
        conversation_reference=None,
        conversation_reference_kind=None,
    )

    assert selected["canonical_target"] == "ETH"
    assert record_selection(
        selected,
        canonical_target="ETH",
        target_source="explicit_current_turn",
        original_target_text="Ethereum",
        target_type="asset",
        conversation_reference=None,
        conversation_reference_kind=None,
    )["canonical_target"] == "ETH"
    with pytest.raises(RuntimeContractImmutableFieldError):
        record_selection(
            selected,
            canonical_target="AAPL",
            target_source="workspace_context",
            original_target_text="Apple",
            target_type="asset",
            conversation_reference=None,
            conversation_reference_kind=None,
        )


def test_complete_run_never_creates_or_reconstructs_a_runtime_contract():
    source = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")
    complete_run_source = source.split("    async def complete_run(", 1)[1].split("    def _terminal_placeholder_response", 1)[0]

    assert "materialize_terminal" in complete_run_source
    assert "create_for_run" not in complete_run_source
    assert "_runtime_contract_projection" in complete_run_source


def test_new_contract_terminal_envelope_reads_persisted_projection_without_artifact_reconstruction():
    now = datetime.now(timezone.utc)
    projection = {
        "projection_version": RUNTIME_CONTRACT_VERSION,
        "contract_id": "contract-run-1",
        "run_id": "run-1",
        "conversation_id": "conversation-1",
        "initial_operation_id": "evaluate_plan",
        "final_operation_id": "evaluate_plan",
        "requested_mode": "EVALUATE",
        "final_mode": "EVALUATE",
        "terminal_status": "completed",
        "response": {
            "mode": "EVALUATE",
            "content": "Een geverifieerd antwoord.",
            "response_source": "v2_runtime",
            "verifier_status": "passed",
        },
    }
    run = SimpleNamespace(
        id="run-1", user_id=7, conversation_id="conversation-1", status="completed", interaction_mode="EVALUATE",
        visibility="visible", response_json={}, policy_json=None, created_at=now, updated_at=now, completed_at=now,
        error_code=None, error_message=None, retryable=False,
    )
    service = FinnV2RunService(session=object())
    service.runtime_contracts = SimpleNamespace(
        get_for_run=lambda **_kwargs: asyncio.sleep(0, result=SimpleNamespace(terminal_projection_json=projection))
    )
    service.delivery.get_delivery_artifacts = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("new contract must not reconstruct artifacts"))

    envelope = asyncio.run(service.envelope_from_run(run))

    assert envelope.runtime_trace == projection
    assert envelope.response.content == "Een geverifieerd antwoord."


def test_new_contract_without_persisted_terminal_projection_never_falls_back_to_legacy_compact():
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="run-missing-projection", user_id=7, conversation_id="conversation-1", status="failed", interaction_mode=None,
        visibility="visible", response_json={}, policy_json=None, created_at=now, updated_at=now, completed_at=now,
        error_code="failure", error_message="failure", retryable=False,
    )
    service = FinnV2RunService(session=object())
    service.runtime_contracts = SimpleNamespace(
        get_for_run=lambda **_kwargs: asyncio.sleep(
            0, result=SimpleNamespace(contract_id="contract-missing", contract_version=RUNTIME_CONTRACT_VERSION, terminal_projection_json=None)
        )
    )
    service.delivery.get_delivery_artifacts = lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not read legacy artifacts"))

    envelope = asyncio.run(service.envelope_from_run(run))

    assert envelope.runtime_trace["error_code"] == "runtime_contract_terminal_projection_missing"
    assert envelope.runtime_trace.get("terminal_projection") != "legacy_compact"


def test_new_contract_migration_has_one_contract_per_run_and_revision_guard():
    source = (ROOT / "scripts" / "migrations" / "2026_09_04_finn_v2_runtime_contract_foundation.py").read_text(encoding="utf-8")
    assert "run_id TEXT NOT NULL UNIQUE" in source
    assert "revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0)" in source
    assert "terminal_projection_json JSONB" in source


def test_owned_worker_lifecycle_passes_only_run_identity_between_sessions():
    source = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")
    owned = source.split("async def run_foundation_lifecycle_owned", 1)[1].split("    def _is_visible_run", 1)[0]
    assert "run_id=run_id" in owned
    assert "complete_run(" in owned
    assert "create_for_run" not in owned


def test_owned_worker_lifecycle_has_a_terminal_deadline_independent_of_delivery():
    source = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")
    owned = source.split("async def run_foundation_lifecycle_owned", 1)[1].split("    def _is_visible_run", 1)[0]

    assert "asyncio.wait_for(" in owned
    assert "lifecycle_deadline_seconds()" in owned
    assert 'error_code="lifecycle_deadline_exceeded"' in owned


def test_selector_persistence_precedes_post_selection_execution_and_has_a_separate_budget():
    orchestrator = (ROOT / "services" / "finn_v2_orchestrator_service.py").read_text(encoding="utf-8")
    lifecycle = (ROOT / "services" / "finn_v2_run_service.py").read_text(encoding="utf-8")

    assert "asyncio.to_thread" in orchestrator
    assert "selector_phase_deadline_seconds" in orchestrator
    assert orchestrator.index("record_selection(") < orchestrator.index("execute_tool_plan(")
    assert orchestrator.index("selection_persisted()") < orchestrator.index("execute_tool_plan(")
    assert "selection_ready.wait()" in lifecycle
    assert "selector_started.wait()" in lifecycle
    assert lifecycle.index("selector_started.wait()") < lifecycle.index("selection_ready.wait()")
    assert "selector_phase_started" in lifecycle
    assert "selector_started()" in orchestrator
    assert "terminal_persistence_reserve_seconds" in lifecycle


def test_selected_capability_uses_the_post_selector_registry_fast_path():
    orchestrator = (ROOT / "services" / "finn_v2_orchestrator_service.py").read_text(encoding="utf-8")
    run_service = FinnV2RunService(session=object())

    assert 'execution_view["initial_operation_id"] == "capability"' in orchestrator
    assert orchestrator.index("capability_fast_path_completed") < orchestrator.index("execute_tool_plan(")

    response = run_service._terminal_placeholder_response(
        interaction_mode="CAPABILITY",
        terminal_status="completed",
        orchestrator={},
        verifier={},
        reasoning={},
        delivery_envelope={},
    )

    assert response["mode"] == "CAPABILITY"
    assert response["verifier_status"] == "registry_grounded"
    assert "tradingcontext" in response["content"]


def test_selector_provider_budget_leaves_time_for_the_persisted_selection(monkeypatch):
    monkeypatch.setenv("FINN_V2_SELECTOR_PHASE_DEADLINE_SECONDS", "35")
    monkeypatch.setenv("FINN_V2_TERMINAL_PERSISTENCE_RESERVE_SECONDS", "2")
    flags = FinnV2FlagService()
    selector = (ROOT / "services" / "finn_v2_structured_operation_selector_service.py").read_text(encoding="utf-8")

    assert flags.selector_provider_timeout_seconds() == 33
    assert flags.selector_max_output_tokens() == 240
    assert "timeout_seconds=selector_timeout_seconds" in (
        ROOT / "services" / "finn_v2_operation_classification_service.py"
    ).read_text(encoding="utf-8")
    assert "selector_timeout_seconds=self.flags.selector_provider_timeout_seconds()" in (
        ROOT / "services" / "finn_v2_orchestrator_service.py"
    ).read_text(encoding="utf-8")
    assert "selector_max_output_tokens=self.flags.selector_max_output_tokens()" in (
        ROOT / "services" / "finn_v2_orchestrator_service.py"
    ).read_text(encoding="utf-8")
    assert "phase_budget_seconds" in selector


def test_worker_dispatch_keeps_the_created_contract_attached_to_the_same_run(monkeypatch):
    """Exercise the production worker entrypoint without replacing it by complete_run."""
    from backend.celery_task import finn_v2_task

    run = SimpleNamespace(id="run-worker-1", user_id=7, status="created")
    created_contracts = {run.id: "contract-run-worker-1"}
    calls = []

    class _Result:
        def scalars(self):
            return SimpleNamespace(first=lambda: run)

    class _Session:
        async def execute(self, _statement):
            return _Result()

        async def commit(self):
            return None

    class _Context:
        async def __aenter__(self):
            return _Session()

        async def __aexit__(self, *_args):
            return False

    class _Dispatches:
        def __init__(self, _session):
            pass

        async def claim(self, **_kwargs):
            return SimpleNamespace(dispatch_id="dispatch-worker-1")

        async def heartbeat(self, **_kwargs):
            calls.append("heartbeat")

        async def mark_completed(self, dispatch_id):
            calls.append(("completed", dispatch_id))

        async def mark_failure(self, **_kwargs):
            raise AssertionError("worker must not fail")

    class _RunService:
        def __init__(self, _session):
            self.runtime_contracts = SimpleNamespace(record_phase_timestamp=self._record_phase_timestamp)

        async def _record_phase_timestamp(self, *, run_id, phase):
            calls.append(("phase", run_id, phase))

        @classmethod
        async def run_foundation_lifecycle_owned(cls, *, run_id, user_id):
            assert created_contracts[run_id] == "contract-run-worker-1"
            run.status = "completed"
            calls.append(("lifecycle", run_id, user_id))

    monkeypatch.setattr(finn_v2_task, "async_session_factory", lambda: _Context())
    monkeypatch.setattr(finn_v2_task, "FinnV2DispatchRepository", _Dispatches)
    monkeypatch.setattr(finn_v2_task, "FinnV2RunService", _RunService)

    assert asyncio.run(finn_v2_task._process_finn_v2_run(run_id=run.id, owner="worker-1")) == run.id
    assert calls == [
        ("phase", run.id, "dispatch_claimed"),
        "heartbeat",
        ("lifecycle", run.id, 7),
        ("completed", "dispatch-worker-1"),
    ]
