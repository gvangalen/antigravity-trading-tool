from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_setup_strategy_journey as probe


def _mock_lifecycle_services(monkeypatch, execute):
    from backend.infrastructure import database
    from backend.infrastructure.repositories import finn_v2_proposal_repository as proposal_repository
    from backend.services import finn_v2_confirmation_service as confirmation_service
    from backend.services import finn_v2_execution_service as execution_service

    @asynccontextmanager
    async def session_factory():
        yield object()

    async def get_proposal(**_kwargs):
        return SimpleNamespace(operation_type="create_setup", payload_hash="synthetic-hash")

    async def issue_token(**_kwargs):
        return "synthetic-token", None

    async def confirm(**_kwargs):
        return SimpleNamespace(confirmed=True)

    monkeypatch.setattr(database, "async_session_factory", session_factory)
    monkeypatch.setattr(proposal_repository, "FinnV2ProposalRepository", lambda _session:
        SimpleNamespace(get_by_id_for_user=get_proposal))
    monkeypatch.setattr(confirmation_service, "FinnV2ConfirmationService", lambda _session:
        SimpleNamespace(issue_confirmation_token=issue_token, confirm=confirm))
    monkeypatch.setattr(execution_service, "FinnV2ExecutionService", lambda _session:
        SimpleNamespace(execute=execute))


@pytest.mark.parametrize("first_status,first_codes", [
    ("blocked", ["proposal_not_confirmed"]),
    ("failed", ["private database detail"]),
])
def test_lifecycle_diagnostic_captures_typed_first_and_replay_status(
    monkeypatch, first_status, first_codes,
):
    async def execute(**_kwargs):
        return SimpleNamespace(status=first_status, error_codes=first_codes,
                               journey_next_step=None, conversation_id="synthetic")

    _mock_lifecycle_services(monkeypatch, execute)
    trace = {}
    with pytest.raises(RuntimeError, match="^journey_replay_failed$"):
        asyncio.run(probe._confirm_and_execute(42, "synthetic-proposal", trace))
    diagnostic = trace["execution_diagnostic"]
    assert diagnostic["operation"] == "create_setup"
    assert diagnostic["first_status"] == first_status
    assert diagnostic["first_codes"] == (
        first_codes if first_status == "blocked" else ["other"])
    assert diagnostic["replay_status"] == first_status
    assert diagnostic["exception_stage"] == "replay_check"
    assert "private database detail" not in str(diagnostic)


def test_lifecycle_diagnostic_captures_raise_before_execution_row(monkeypatch):
    async def execute(**_kwargs):
        raise ValueError("private proposal or database detail")

    _mock_lifecycle_services(monkeypatch, execute)
    trace = {}
    with pytest.raises(ValueError, match="private proposal"):
        asyncio.run(probe._confirm_and_execute(42, "synthetic-proposal", trace))
    diagnostic = trace["execution_diagnostic"]
    assert diagnostic["first_status"] == "raised"
    assert diagnostic["replay_status"] == "not_called"
    assert diagnostic["exception_stage"] == "first_execute"
    assert diagnostic["exception_class"] == "ValueError"
    assert "private proposal" not in str(diagnostic)


def test_lifecycle_diagnostic_separates_replay_mismatch(monkeypatch):
    results = iter((
        SimpleNamespace(status="succeeded", error_codes=[],
                        journey_next_step={"step": "strategy"}, conversation_id="synthetic"),
        SimpleNamespace(status="already_executed", error_codes=[],
                        journey_next_step={"step": "paper"}, conversation_id="synthetic"),
    ))

    async def execute(**_kwargs):
        return next(results)

    _mock_lifecycle_services(monkeypatch, execute)
    trace = {}
    with pytest.raises(RuntimeError, match="^journey_replay_failed$"):
        asyncio.run(probe._confirm_and_execute(42, "synthetic-proposal", trace))
    diagnostic = trace["execution_diagnostic"]
    assert diagnostic["first_status"] == "succeeded"
    assert diagnostic["replay_status"] == "already_executed"
    assert diagnostic["next_step_match"] is False
    assert diagnostic["exception_stage"] == "replay_check"


def test_runner_uses_existing_live_exchange_guard(monkeypatch):
    from backend.engine import trading_bot_execution as execution
    from backend.infrastructure import database

    async def case(_namespace, _owner, _trace):
        assert execution._execute_on_exchange_sync is not original_exchange
        return {"result": "PASS"}

    async def dispose():
        pass

    original_exchange = execution._execute_on_exchange_sync
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_SETUP_STRATEGY_JOURNEY", "1")
    monkeypatch.setattr(probe, "_case", case)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    result = probe.run("qa-20261122-1-abcdef12-34567890")
    assert result["result"] == "PASS"
    assert result["live_calls"] == 0
    assert execution._execute_on_exchange_sync is original_exchange


def test_runner_projects_only_typed_lifecycle_diagnostic_on_failure(monkeypatch):
    from backend.infrastructure import database

    async def case(_namespace, _owner, trace):
        trace["stage"] = "setup_confirmation"
        trace["fixture_state"] = "quarantined"
        trace["execution_diagnostic"] = {
            "operation": "create_setup", "stage": "replay_check",
            "first_status": "blocked", "first_codes": ["proposal_not_confirmed"],
            "replay_status": "blocked", "replay_codes": ["proposal_not_confirmed"],
            "next_step_match": True, "exception_class": "RuntimeError",
            "exception_stage": "replay_check",
        }
        raise RuntimeError("journey_replay_failed")

    async def dispose():
        pass

    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_SETUP_STRATEGY_JOURNEY", "1")
    monkeypatch.setattr(probe, "_case", case)
    monkeypatch.setattr(database, "engine", SimpleNamespace(dispose=dispose))
    result = probe.run("qa-20261122-1-abcdef12-34567890")
    assert result["result"] == "FAIL"
    assert result["reason"] == "journey_replay_failed"
    assert result["execution_diagnostic"]["first_status"] == "blocked"
    assert result["execution_diagnostic"]["replay_status"] == "blocked"
    assert "42" not in str(result) and "synthetic" not in str(result)


def test_owner_binding_requires_all_protected_flags(monkeypatch):
    namespace = "qa-20261122-1-abcdef12-34567890"
    monkeypatch.setenv("FINN_QA_USER_ID", "42")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_ACTIONS", "1")
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "1")
    monkeypatch.delenv("FINN_QA_ALLOW_SETUP_STRATEGY_JOURNEY", raising=False)
    with pytest.raises(RuntimeError, match="^journey_not_authorized$"):
        probe._bound_owner(namespace)
    monkeypatch.setenv("FINN_QA_ALLOW_SETUP_STRATEGY_JOURNEY", "1")
    assert probe._bound_owner(namespace) == 42
    monkeypatch.setenv("FINN_QA_ALLOW_FIXTURE_EXECUTION", "0")
    with pytest.raises(RuntimeError, match="^journey_not_authorized$"):
        probe._bound_owner(namespace)


def test_full_journey_keeps_bot_uncreated_and_cleans(monkeypatch):
    events = []
    namespace = "qa-20261122-1-abcdef12-34567890"
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args, **_kwargs: (70, 80, ""))
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *_args, **_kwargs: events.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: events.append("quarantine"))
    baseline = {key: 0 for key in ("setups", "strategies", "bot_orders", "bot_executions",
                                   "exchange_keys", "active_or_live_bots", "btc_watchlist")}
    baseline["bot_configs"] = 1
    after = dict(baseline, setups=1, strategies=1)
    snapshots = iter((baseline, baseline, dict(baseline, setups=1), after))
    monkeypatch.setattr(probe, "_snapshot", lambda _user_id: next(snapshots))
    turns = iter((
        {"status": "completed", "conversation_id": "conv", "proposal_id": "setup", "confirmation_required": True,
         "operation_id": "create_setup", "dispatch_count": 1, "attempt_count": 1},
        {"status": "clarification_required", "conversation_id": "conv", "proposal_id": None,
         "operation_id": "clarify_request", "guided_operation": "create_strategy", "supplied_inputs": {"setup_id": 90},
         "dispatch_count": 1, "attempt_count": 1},
        {"status": "completed", "conversation_id": "conv", "proposal_id": "strategy", "confirmation_required": True,
         "operation_id": "create_strategy", "supplied_inputs": {"setup_id": 90}, "dispatch_count": 1, "attempt_count": 1},
        {"status": "clarification_required", "conversation_id": "conv", "proposal_id": None,
         "operation_id": "clarify_request", "guided_operation": "create_bot", "supplied_inputs": {"strategy_id": 91},
         "dispatch_count": 1, "attempt_count": 1},
    ))
    async def turn(*_args, **_kwargs):
        return next(turns)
    async def confirm(_user_id, proposal_id, trace):
        trace["confirmed_count"] = trace.get("confirmed_count", 0) + 1
        trace["executed_count"] = trace.get("executed_count", 0) + 1
        if proposal_id == "setup":
            return {"conversation_id": "conv", "next_step": {"step": "strategy", "setup_id": 90}}
        return {"conversation_id": "conv", "next_step": {"step": "paper", "setup_id": 90, "strategy_id": 91}}
    async def card(*_args):
        return {"id": "card"}
    async def discuss(*_args):
        events.append("discuss")
    async def resolved(*_args):
        events.append("resolved")
    monkeypatch.setattr(probe, "_turn", turn)
    monkeypatch.setattr(probe, "_confirm_and_execute", confirm)
    monkeypatch.setattr(probe, "_card", card)
    monkeypatch.setattr(probe, "_discuss_card", discuss)
    monkeypatch.setattr(probe, "_wait_resolved", resolved)
    monkeypatch.setattr(probe, "_saved_pair", lambda *_args: {"setup_id": 90, "strategy_id": 91})
    trace = {"stage": "seed", "fixture_state": "not_created"}
    result = asyncio.run(probe._case(namespace, 42, trace))
    assert result["result"] == "PASS"
    assert result["replay"] and result["no_bot_or_order"]
    assert events == ["discuss", "resolved", "discuss", "cleanup"]
    assert trace["fixture_state"] == "cleaned"


def test_failed_guided_turn_quarantines(monkeypatch):
    events = []
    baseline = {key: 0 for key in ("setups", "strategies", "bot_orders", "bot_executions",
                                   "exchange_keys", "active_or_live_bots", "btc_watchlist")}
    baseline["bot_configs"] = 1
    monkeypatch.setattr(probe.fixture, "_seed", lambda *_args, **_kwargs: (70, 80, ""))
    monkeypatch.setattr(probe.fixture, "_cleanup", lambda *_args, **_kwargs: events.append("cleanup"))
    monkeypatch.setattr(probe.fixture, "_quarantine", lambda *_args: events.append("quarantine"))
    monkeypatch.setattr(probe, "_snapshot", lambda _user_id: baseline)
    async def bad_turn(*_args, **_kwargs):
        return {"status": "failed", "conversation_id": "conv", "proposal_id": None}
    monkeypatch.setattr(probe, "_turn", bad_turn)
    with pytest.raises(RuntimeError, match="^journey_setup_proposal_missing$"):
        asyncio.run(probe._case("qa-20261122-1-abcdef12-34567890", 42,
                                {"stage": "seed", "fixture_state": "not_created"}))
    assert events == ["quarantine"]
