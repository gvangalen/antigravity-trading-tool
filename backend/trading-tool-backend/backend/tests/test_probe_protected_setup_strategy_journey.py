from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.scripts import probe_protected_setup_strategy_journey as probe


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
