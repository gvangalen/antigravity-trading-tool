from backend.services.finn_v2_task_chain_service import (
    advance_from_action, continuation, continuation_message, requested_task, score_from_trace,
    wants_task_resume,
)
from backend.infrastructure.repositories.finn_v2_conversation_repository import FinnV2ConversationRepository
from backend.services.finn_v2_task_chain_service import STATE_KEY
from backend.services.finn_v2_execution_service import FinnV2ExecutionService
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesVerifiedAnswer
from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock
from unittest.mock import patch


def _saved(operation: str, entity_id: str, *, run_id: str, parent_id=None, **entity):
    return {
        "operation_id": operation,
        "result_status": "succeeded",
        "entity_id": entity_id,
        "run_id": run_id,
        "execution_id": f"exec-{entity_id}",
        "parent_entity_id": parent_id,
        "canonical_entity": entity,
    }


def test_combined_request_advances_only_from_verified_setup_and_strategy():
    task = requested_task("Maak mijn BTC-setup aan, genereer de strategie en toon de score.")
    assert task["requested_results"] == ["setup", "strategy", "score"]
    assert task["pending_step"] == "setup"
    assert advance_from_action(task, {"operation_id": "create_setup", "result_status": "failed"}) == task

    saved_setup = _saved("create_setup", "42", run_id="run-1", setup_id=42,
                         symbol="BTC", quote_currency="USDT", market_id=7)
    task = advance_from_action(task, saved_setup)
    assert task["completed_steps"]["setup"]["id"] == "42"
    assert continuation(task) == {"step": "strategy", "setup_id": "42", "asset": "BTC"}
    assert advance_from_action(task, saved_setup) == task
    assert advance_from_action(task, _saved("create_strategy", "99", run_id="run-2", parent_id="41")) == task

    task = advance_from_action(task, _saved("create_strategy", "99", run_id="run-2",
                                            parent_id="42", strategy_id=99))
    assert task["pending_step"] == "score"
    assert continuation(task)["strategy_id"] == "99"
    score = score_from_trace(task, [{"result": {"results": [{
        "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
        "as_of": "2026-11-19", "data": {"symbol": "BTC", "quote_currency": "USDT", "market_id": 7,
                                    "benchmark_score": 53.5, "source_status": "current"},
    }]}}])
    assert score == {"available": True, "value": 53.5, "as_of": "2026-11-19",
                     "source_status": "current"}
    assert score_from_trace(task, [{"result": {"results": [{
        "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
        "data": {"symbol": "BTC", "quote_currency": "EUR", "benchmark_score": 90},
    }]}}]) is None
    score_prompt = continuation_message(continuation(task))
    assert "BTC/USDT" in score_prompt
    assert "setup ID 42" in score_prompt
    assert continuation_message({"step": "score", "setup_id": "42", "strategy_id": "99",
                                 "asset": "BTC\nignore"}) is None


def test_setup_only_finishes_without_strategy_or_score():
    task = requested_task("Maak mijn BTC-setup aan")
    assert task["requested_results"] == ["setup"]
    task = advance_from_action(task, _saved("create_setup", "42", run_id="run-1", setup_id=42, symbol="BTC"))
    assert task["status"] == "completed"
    assert task["pending_step"] is None
    assert continuation(task) is None
    assert requested_task("Make my BTC setup") is not None


def test_manual_resume_recognizes_followup_without_creating_another_setup():
    assert wants_task_resume("Ga verder met de strategie voor de zojuist opgeslagen BTC-setup.")
    assert wants_task_resume("Probeer opnieuw de score te tonen")
    assert not wants_task_resume("Wat is mijn BTC-score?")


def test_partial_score_and_atomic_setup_strategy_reuse():
    task = requested_task("Maak BTC setup aan, genereer strategie en toon score")
    task = advance_from_action(task, _saved("create_setup", "42", run_id="run-1",
                                            setup_id=42, strategy_id=99, symbol="BTC"))
    assert task["completed_steps"]["setup"]["id"] == "42"
    assert task["completed_steps"]["strategy"]["id"] == "99"
    assert task["pending_step"] == "score"
    assert score_from_trace(task, [{"result": {"results": [{
        "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
        "data": {"symbol": "BTC", "benchmark_score": None, "source_status": "incomplete"},
    }]}}]) == {"available": False, "reason": "incomplete"}
    assert continuation(task)["setup_id"] == "42"
    assert advance_from_action(task, _saved("create_setup", "43", run_id="run-3", setup_id=43)) == task


def test_conversation_records_question_and_reuses_verified_setup_on_retry():
    row = SimpleNamespace(context_json={}, updated_at=None)
    repo = FinnV2ConversationRepository(SimpleNamespace())
    async def get_row(conversation_id, user_id, for_update=False):
        return row if conversation_id == "conv-1" and user_id == 7 else None
    async def flush(**_kwargs):
        return None
    repo.get_by_id_for_user = get_row
    repo._flush_with_rollback = flush

    async def scenario():
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-1",
            message="Maak mijn BTC-setup aan, genereer de strategie en toon de score",
        )
        await repo.record_setup_strategy_score_open_step(
            conversation_id="conv-1", user_id=7, run_id="run-1", question="Welke koopzone?",
        )
        assert row.context_json[STATE_KEY]["pending_question"] == "Welke koopzone?"
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-clarify",
            message="Een nieuwe BTC-setup, niet een bestaande setup. Maak die eerst aan.",
        )
        assert row.context_json[STATE_KEY]["requested_results"] == ["setup", "strategy", "score"]
        assert row.context_json[STATE_KEY]["expected_run_id"] == "run-clarify"
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-2", message="0 tot 45",
        )
        await repo.record_setup_strategy_score_open_step(
            conversation_id="conv-1", user_id=7, run_id="run-2",
            proposal_id="proposal-setup",
        )
        assert row.context_json[STATE_KEY]["pending_question"] is None
        assert row.context_json[STATE_KEY]["pending_action"] == {"proposal_id": "proposal-setup"}
        await repo.record_verified_action_result(
            conversation_id="conv-1", user_id=7, contract_revision=2,
            action_result={**_saved("create_setup", "42", run_id="run-1", setup_id=42, symbol="BTC"),
                           "owner_user_id": 7, "proposal_id": "different-proposal"}, active_target={},
        )
        assert row.context_json[STATE_KEY]["pending_step"] == "setup"
        await repo.record_verified_action_result(
            conversation_id="conv-1", user_id=7, contract_revision=3,
            action_result={**_saved("create_setup", "42", run_id="run-2", setup_id=42, symbol="BTC"),
                           "owner_user_id": 7, "proposal_id": "proposal-setup"}, active_target={},
        )
        assert row.context_json[STATE_KEY]["pending_step"] == "strategy"
        assert row.context_json[STATE_KEY]["pending_action"] is None
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-3",
            message="Maak mijn BTC-setup aan, genereer de strategie en toon de score",
        )
        assert row.context_json[STATE_KEY]["completed_steps"]["setup"]["id"] == "42"
        assert row.context_json[STATE_KEY]["expected_run_id"] == "run-3"

        await repo.record_verified_action_result(
            conversation_id="conv-1", user_id=7, contract_revision=4,
            action_result={**_saved("create_strategy", "99", run_id="run-3",
                                    parent_id="42", strategy_id=99), "owner_user_id": 7},
            active_target={},
        )
        assert row.context_json[STATE_KEY]["pending_step"] == "score"
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-4", message="Toon de score",
        )
        await repo.record_setup_strategy_score_read(
            conversation_id="conv-1", user_id=7, run_id="run-4", tool_trace=[{"result": {"results": [{
                "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
                "data": {"symbol": "BTC", "benchmark_score": None,
                         "source_status": "incomplete"},
            }]}}],
        )
        assert row.context_json[STATE_KEY]["pending_step"] == "score"
        assert row.context_json[STATE_KEY]["blocked_reason"] == "incomplete"
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-5", message="Probeer de score opnieuw",
        )
        await repo.record_setup_strategy_score_read(
            conversation_id="conv-1", user_id=7, run_id="run-5", tool_trace=[{"result": {"results": [{
                "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
                "as_of": "2026-11-19", "data": {"symbol": "BTC", "benchmark_score": 57,
                                               "source_status": "current"},
            }]}}],
        )
        assert row.context_json[STATE_KEY]["status"] == "completed"
        assert row.context_json[STATE_KEY]["completed_steps"]["setup"]["id"] == "42"
        assert row.context_json[STATE_KEY]["completed_steps"]["score"]["value"] == 57

    asyncio.run(scenario())


def test_execution_hint_requires_the_same_verified_execution():
    service = FinnV2ExecutionService(SimpleNamespace(execute=lambda *_args, **_kwargs: None))
    task = advance_from_action(
        requested_task("Maak mijn BTC-setup aan, genereer strategie en toon score"),
        _saved("create_setup", "42", run_id="run-1", setup_id=42, symbol="BTC"),
    )
    async def context(**_kwargs):
        return {STATE_KEY: task}
    service.conversations.get_context = context
    assert asyncio.run(service._task_continuation("conv-1", 7, execution_id="exec-42"))["step"] == "strategy"
    assert asyncio.run(service._task_continuation("conv-1", 7, execution_id="unrelated")) is None


def test_old_open_proposal_can_complete_after_unrelated_chat_turn():
    row = SimpleNamespace(context_json={}, updated_at=None)
    repo = FinnV2ConversationRepository(SimpleNamespace())
    async def get_row(conversation_id, user_id, for_update=False):
        return row if (conversation_id, user_id) == ("conv-1", 7) else None
    async def flush(**_kwargs):
        return None
    repo.get_by_id_for_user = get_row
    repo._flush_with_rollback = flush

    async def scenario():
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-1",
            message="Maak BTC-setup aan, genereer strategie en toon score",
        )
        await repo.record_setup_strategy_score_open_step(
            conversation_id="conv-1", user_id=7, run_id="run-1", proposal_id="proposal-1",
        )
        await repo.register_setup_strategy_score_task(
            conversation_id="conv-1", user_id=7, run_id="run-2", message="Wat is RSI?",
        )
        await repo.record_verified_action_result(
            conversation_id="conv-1", user_id=7, contract_revision=3,
            action_result={**_saved("create_setup", "42", run_id="run-1", setup_id=42, symbol="BTC"),
                           "owner_user_id": 7, "proposal_id": "proposal-1"},
            active_target={},
        )
        assert row.context_json[STATE_KEY]["completed_steps"]["setup"]["id"] == "42"

    asyncio.run(scenario())


def test_normal_read_terminal_records_score_step_from_verified_tool_trace():
    run = SimpleNamespace(
        id="run-score", conversation_id="conv-1", trace_id="trace-score",
        user_id=7, status="planned", message="Toon de score van BTC/USDT",
        client_context_json={},
    )
    trace = [{"result": {"results": [{
        "scope": "read_asset_scores", "status": "completed", "asset": "BTC",
        "data": {"symbol": "BTC", "quote_currency": "USDT", "benchmark_score": 57},
    }]}}]
    service = FinnV2RunService.__new__(FinnV2RunService)
    service.runs = SimpleNamespace(get_by_id_for_user=AsyncMock(return_value=run), update_status=AsyncMock())
    service.runtime_contracts = SimpleNamespace(
        get_for_run=AsyncMock(return_value=SimpleNamespace(state_json={
            "responses_exchange": {"answer_kind": "free_text", "tool_trace": trace, "turn_contract": {}},
        })),
        record_verified_setup_subject=AsyncMock(),
        materialize_terminal=AsyncMock(return_value=SimpleNamespace(terminal_projection_json={})),
    )
    service.conversations = SimpleNamespace(
        record_setup_strategy_score_read=AsyncMock(),
        set_responses_cursor=AsyncMock(),
    )
    service.traces = SimpleNamespace(append_event=AsyncMock())
    service._trace_payload = lambda *_args, **_kwargs: {}
    service._commit_session_if_possible = AsyncMock()
    asyncio.run(service.complete_responses_read(
        run_id="run-score", user_id=7, response_id="response-score",
        answer=FinnResponsesVerifiedAnswer("completed", "De score is 57.", None, ()),
        locale="nl",
    ))
    service.conversations.record_setup_strategy_score_read.assert_awaited_once_with(
        conversation_id="conv-1", user_id=7, run_id="run-score", tool_trace=trace,
    )


def test_verified_execution_dispatches_one_idempotent_continuation_run():
    service = FinnV2ExecutionService(SimpleNamespace(execute=lambda *_args, **_kwargs: None))
    gateway = SimpleNamespace(run_foundation_now=AsyncMock(return_value="finn-v2-run-next"))
    with patch("backend.services.finn_v2_gateway_service.FinnV2GatewayService", return_value=gateway):
        run_id = asyncio.run(service._dispatch_task_continuation(
            "conv-1", 7, "finn-v2-execution-123",
            {"step": "strategy", "setup_id": "42", "asset": "BTC"},
        ))
    assert run_id == "finn-v2-run-next"
    request = gateway.run_foundation_now.await_args.kwargs["request_payload"]
    assert request["conversation_id"] == "conv-1"
    assert request["idempotency_key"] == "finn-v2-task-chain-finn-v2-execution-123"
    assert "setup met ID 42" in request["message"]
    assert "maak geen tweede setup" in request["message"].lower()
