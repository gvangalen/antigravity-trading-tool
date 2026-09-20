import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.services.finn_v2_json_safety import to_json_safe
from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.finn_v2_proposal_service import FinnV2ProposalService


class _Session:
    def __init__(self):
        self.commits = 0

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1


def test_execution_rejects_update_when_persisted_before_state_changed_after_proposal():
    before_state = {"timeframe": "1W"}
    revision = FinnV2ProposalService._target_revision("setup", 9, 7, before_state)
    proposal = SimpleNamespace(
        operation_type="update_setup",
        user_id=7,
        payload_json={"change": {
            "setup_id": 9,
            "changed_fields": {"timeframe": "1D"},
            "before_state": before_state,
            "target_revision": revision,
        }},
    )

    FinnV2ExecutionService._assert_target_revision(
        proposal=proposal,
        current_entity={"id": 9, "timeframe": "1W"},
    )
    try:
        FinnV2ExecutionService._assert_target_revision(
            proposal=proposal,
            current_entity={"id": 9, "timeframe": "4H"},
        )
    except ValueError as exc:
        assert str(exc) == "proposal_target_changed"
    else:
        raise AssertionError("a stale update proposal must not execute")


def test_execution_service_records_postcondition_hash_on_success():
    session = _Session()
    service = FinnV2ExecutionService(session=session)
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
    assert session.commits == 1
    assert workflow_events == [{
        "run_id": "run-1",
        "proposal_id": "proposal-1",
        "operation_id": "update_setup",
        "payload_hash": "hash-1",
        "event": "execution_started",
        "execution_id": result.execution_id,
    }, {
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
                "canonical_entity": {"setup_id": 9},
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


def test_execution_returns_run_conversation_when_action_result_write_has_no_row():
    session = _Session()
    service = FinnV2ExecutionService(session=session)
    service.runtime_contracts.record_proposal_lifecycle = lambda **kwargs: asyncio.sleep(0)
    # Repository implementations may persist the result without returning a
    # refreshed ORM row. The public execution response must still carry the
    # run's conversation binding for an immediate natural-language follow-up.
    service.runtime_contracts.record_action_result = lambda **kwargs: asyncio.sleep(0, result=None)
    service.runtime_contracts.get_for_run = lambda **kwargs: asyncio.sleep(
        0, result=SimpleNamespace(conversation_id="finn-v2-conversation-after-confirmation")
    )
    service.repo.get_by_idempotency_key_for_user = lambda **kwargs: asyncio.sleep(0, result=None)
    service.repo.get_for_proposal = lambda **kwargs: asyncio.sleep(0, result=None)
    service.proposals.get_by_id_for_user = lambda **kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(
            id="proposal-conversation-fallback",
            run_id="run-conversation-fallback",
            user_id=7,
            operation_type="update_setup",
            payload_hash="hash-conversation-fallback",
            payload_json={"change": {"setup_id": 9, "changed_fields": {"timeframe": "1D"}}},
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
        ),
    )
    service.gates.check_execution_eligibility = lambda **kwargs: asyncio.sleep(
        0, result=SimpleNamespace(eligible=True, dict=lambda: {"eligible": True})
    )
    service.repo.create = lambda **kwargs: asyncio.sleep(0, result=SimpleNamespace(**kwargs))
    service.adapters.get = lambda _operation_type: (
        lambda _user_id, _payload: asyncio.sleep(0, result={"ok": True, "setup_id": 9})
    )
    service.adapters.postcondition_hash = lambda *_args, **_kwargs: asyncio.sleep(0, result="post-hash")

    result = asyncio.run(
        service.execute(
            proposal_id="proposal-conversation-fallback",
            user_id=7,
            idempotency_key="idem-conversation-fallback",
            expected_payload_hash="hash-conversation-fallback",
        )
    )

    assert result.status == "succeeded"
    assert result.conversation_id == "finn-v2-conversation-after-confirmation"


def test_execution_mirrors_only_verified_postcondition_into_conversation():
    service = FinnV2ExecutionService(session=_Session())
    captured = {}
    service.conversations.record_verified_action_result = lambda **kwargs: asyncio.sleep(0, result=captured.update(kwargs))
    runtime_contract = SimpleNamespace(
        revision=12,
        state_json={
            "identity": {"conversation_id": "conversation-1", "user_id": 7},
            "action_result": {
                "operation_id": "update_strategy",
                "entity_type": "strategy",
                "entity_id": "52",
                "owner_user_id": 7,
                "result_status": "succeeded",
                "conversation_id": "conversation-1",
            },
            "canonical_entity_target": {
                "entity_type": "strategy", "entity_id": "52", "owner_id": 7,
            },
        },
    )

    asyncio.run(service._record_verified_conversation_target(runtime_contract))

    assert captured["conversation_id"] == "conversation-1"
    assert captured["user_id"] == 7
    assert captured["contract_revision"] == 12
    assert captured["action_result"]["entity_id"] == "52"


def test_execution_does_not_mirror_deleted_target_as_a_live_reference():
    service = FinnV2ExecutionService(session=_Session())
    calls = []
    service.conversations.record_verified_action_result = lambda **kwargs: asyncio.sleep(0, result=calls.append(kwargs))
    runtime_contract = SimpleNamespace(
        revision=12,
        state_json={
            "identity": {"conversation_id": "conversation-1", "user_id": 7},
            "action_result": {
                "operation_id": "delete_strategy",
                "entity_type": "strategy",
                "entity_id": "52",
                "owner_user_id": 7,
                "result_status": "succeeded",
            },
        },
    )

    asyncio.run(service._record_verified_conversation_target(runtime_contract))

    assert calls == []


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


def test_action_result_projects_the_committed_entity_snapshot():
    proposal = SimpleNamespace(
        id="proposal-strategy",
        run_id="run-strategy",
        user_id=7,
        operation_type="create_strategy",
        payload_json={"change": {"strategy_fields": {"setup_id": 12, "name": "Apple Swing"}}},
    )
    execution = SimpleNamespace(id="execution-strategy", status="succeeded", completed_at=datetime.now(timezone.utc))

    action_result = FinnV2ExecutionService._action_result(
        proposal=proposal,
        execution=execution,
        result={"id": 44, "name": "Apple Swing", "symbol": "AAPL", "timeframe": "1D", "setup_id": 12},
    )

    assert action_result["canonical_name"] == "Apple Swing"
    assert action_result["canonical_entity"] == {
        "id": 44,
        "name": "Apple Swing",
        "symbol": "AAPL",
        "timeframe": "1D",
        "setup_id": 12,
    }


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
