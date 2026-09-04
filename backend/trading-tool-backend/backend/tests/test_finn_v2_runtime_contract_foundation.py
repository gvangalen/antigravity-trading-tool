from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.domain.finn_v2_runtime_contract import (
    RUNTIME_CONTRACT_VERSION,
    RuntimeContractImmutableFieldError,
    new_runtime_contract_state,
    record_initial_intent,
    terminal_projection,
)
from backend.services.finn_v2_run_service import FinnV2RunService


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
        @classmethod
        async def run_foundation_lifecycle_owned(cls, *, run_id, user_id):
            assert created_contracts[run_id] == "contract-run-worker-1"
            calls.append(("lifecycle", run_id, user_id))

    monkeypatch.setattr(finn_v2_task, "async_session_factory", lambda: _Context())
    monkeypatch.setattr(finn_v2_task, "FinnV2DispatchRepository", _Dispatches)
    monkeypatch.setattr(finn_v2_task, "FinnV2RunService", _RunService)

    assert asyncio.run(finn_v2_task._process_finn_v2_run(run_id=run.id, owner="worker-1")) == run.id
    assert calls == ["heartbeat", ("lifecycle", run.id, 7), ("completed", "dispatch-worker-1")]
