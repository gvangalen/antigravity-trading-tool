import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_execution_service import FinnV2ExecutionService


class _Session:
    async def flush(self):
        return None


def test_execution_service_records_postcondition_hash_on_success():
    service = FinnV2ExecutionService(session=_Session())
    workflow_events = []
    action_results = []
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0, result=workflow_events.append(kwargs))
    service.runtime_contracts.record_action_result = lambda **kwargs: asyncio.sleep(0, result=action_results.append(kwargs))
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(0, result=None)
    service.repo.get_for_proposal = lambda **kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="proposal-1",
            run_id="run-1",
            user_id=7,
            operation_type="update_setup",
            payload_hash="hash-1",
            payload_json={"change": {"setup_id": 9, "changed_fields": {"name": "BTC setup"}}},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    service.gates.check_execution_eligibility = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(eligible=True, dict=lambda: {"eligible": True}),
    )
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.adapters.get = lambda operation_type: (lambda user_id, payload: asyncio.sleep(0, result={"ok": True, "setup_id": 9}))
    service.adapters.postcondition_hash = lambda operation_type, **kwargs: asyncio.sleep(0, result="post-hash-1")

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-1",
            user_id=7,
            idempotency_key="idem-5678",
            expected_payload_hash="hash-1",
        )
    )

    assert result.status == "succeeded"
    assert result.postcondition_hash == "post-hash-1"
    assert workflow_events == [{
        "run_id": "run-1",
        "proposal_id": "proposal-1",
        "operation_id": "update_setup",
        "payload_hash": "hash-1",
        "event": "execution_succeeded",
        "execution_id": result.execution_id,
    }]
    assert action_results == [{
        "run_id": "run-1",
        "action_result": {
            "operation_id": "update_setup",
            "entity_type": "setup",
            "entity_id": "9",
            "canonical_name": None,
            "owner_user_id": 7,
            "parent_entity_type": None,
            "parent_entity_id": None,
            "proposal_id": "proposal-1",
            "execution_id": result.execution_id,
            "result_status": "succeeded",
            "created_at": result.completed_at.isoformat(),
            "updated_at": result.completed_at.isoformat(),
            "conversation_id": None,
            "run_id": "run-1",
        },
    }]


def test_execution_service_normalizes_adapter_results_before_json_persistence_and_hashing():
    service = FinnV2ExecutionService(session=_Session())
    captured = {}
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0)
    service.runtime_contracts.record_action_result = lambda **kwargs: asyncio.sleep(0)
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(0, result=None)
    service.repo.get_for_proposal = lambda **kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="proposal-decimal",
            run_id="run-decimal",
            user_id=7,
            operation_type="update_strategy",
            payload_hash="hash-decimal",
            payload_json={"change": {"strategy_id": 9, "changed_fields": {"base_amount": 120}}},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    service.gates.check_execution_eligibility = lambda **kwargs: asyncio.sleep(
        0, result=SimpleNamespace(eligible=True, dict=lambda: {"eligible": True})
    )
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.adapters.get = lambda operation_type: (
        lambda user_id, payload: asyncio.sleep(0, result={"base_amount": Decimal("120.00")})
    )

    async def _postcondition(operation_type, **kwargs):
        captured["payload"] = kwargs["payload"]
        return "post-hash-decimal"

    service.adapters.postcondition_hash = _postcondition

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-decimal",
            user_id=7,
            idempotency_key="idem-decimal",
            expected_payload_hash="hash-decimal",
        )
    )

    assert result.status == "succeeded"
    assert captured["payload"] == {"base_amount": "120.00"}


def test_action_result_accepts_scalar_asset_result_without_failing_execution():
    proposal = SimpleNamespace(
        id="proposal-asset",
        run_id="run-asset",
        user_id=7,
        operation_type="select_asset",
        payload_json={"change": {"asset": "SOL"}, "target": {"asset": "SOL"}},
    )
    execution = SimpleNamespace(id="execution-asset", status="succeeded", completed_at=datetime.now(timezone.utc))

    action_result = FinnV2ExecutionService._action_result(
        proposal=proposal,
        execution=execution,
        result={"ok": True, "asset": "SOL"},
    )

    assert action_result["entity_type"] == "asset"
    assert action_result["canonical_name"] == "SOL"
    assert action_result["result_status"] == "succeeded"


def test_strategy_repository_normalizes_decimal_payload_before_json_encoding():
    """A single strategy-field update retains Decimal values from its row."""
    from backend.infrastructure.repositories.strategy_repository import StrategyRepository

    captured = {}

    class _RepositorySession:
        async def execute(self, _query, params):
            captured.update(params)
            return SimpleNamespace(rowcount=1)

    repository = StrategyRepository(_RepositorySession())
    updated = asyncio.run(repository.update_strategy(
        strategy_id=9,
        user_id=7,
        payload={"base_amount": Decimal("100.00"), "entry": Decimal("4.5")},
        existing_setup_type="trade",
        raw_data={"base_amount": Decimal("100.00"), "entry": Decimal("4.5")},
    ))

    assert updated == 1
    assert '"100.00"' in captured["data"]


def test_execution_service_persists_json_safe_gate_payload_when_blocked():
    service = FinnV2ExecutionService(session=_Session())
    workflow_events = []
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0, result=workflow_events.append(kwargs))
    captured = {}
    gate_payload = {
        "eligible": False,
        "checked_at": datetime.now(timezone.utc),
        "blocking_codes": ["proposal_not_confirmed"],
    }
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(0, result=None)
    service.repo.get_for_proposal = lambda **kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="proposal-1",
            run_id="run-1",
            user_id=7,
            operation_type="watchlist_add",
            payload_hash="hash-1",
            payload_json={"change": {"asset": "ETH", "operation": "add"}},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    service.gates.check_execution_eligibility = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            eligible=False,
            blocking_codes=["proposal_not_confirmed"],
            dict=lambda: gate_payload,
        ),
    )

    async def _capture(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(started_at=datetime.now(timezone.utc), **kwargs)

    service.repo.create = _capture

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-1",
            user_id=7,
            idempotency_key="idem-91011",
            expected_payload_hash="hash-1",
        )
    )

    assert result.status == "blocked"
    assert captured["result_json"] == to_json_safe(gate_payload)
    assert isinstance(captured["result_json"]["checked_at"], str)
    assert workflow_events[0]["event"] == "execution_blocked"
