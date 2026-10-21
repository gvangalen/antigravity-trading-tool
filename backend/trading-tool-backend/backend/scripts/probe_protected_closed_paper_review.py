"""Protected QA round trip: two Paper fills, closed dossier and confirmed lesson.

The owner is inactive, has no exchange keys, and is retained disabled as
private QA evidence. This module never opens a Live order or exports IDs.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Callable

from backend.scripts import probe_protected_auto_paper_history as fixture


class ClosedPaperChatTurnFailure(RuntimeError):
    """Carry only bounded terminal metadata out of the protected chat probe."""

    def __init__(self, turn: str, envelope):
        super().__init__(f"closed_paper_review_chat_{turn}_failed")
        self.terminal_status = getattr(envelope, "status", None)
        self.typed_error_code = getattr(envelope, "error_code", None)
        response = getattr(envelope, "response", None)
        self.response_present = response is not None
        self.response_source = getattr(response, "response_source", None)
        self.verifier_status = getattr(response, "verifier_status", None)
        self.evidence_count = len(getattr(response, "evidence", ()) or ())
        self.review_read_diagnostic: dict[str, object] = {}


class ClosedPaperProbeStageFailure(RuntimeError):
    """Identify the failed protected phase without exporting its exception."""

    ALLOWED_PHASES = frozenset({
        "binding", "seed", "prepare_entry", "paper_buy", "paper_sell", "analysis",
        "dossier", "chat", "orders", "cleanup",
    })
    ALLOWED_CAUSES = frozenset({
        "closed_paper_entry_decision_missing", "closed_paper_open_fill_missing",
        "closed_paper_sell_not_filled", "closed_paper_review_projection_failed",
        "closed_paper_review_analysis_failed", "closed_paper_review_missing",
        "closed_paper_review_duplicate", "closed_paper_lesson_not_readable",
        "closed_paper_review_chat_unexpected_action",
        "closed_paper_review_chat_evidence_missing",
        "closed_paper_review_chat_lesson_missing",
        "closed_paper_review_chat_followup_context_or_action",
        "closed_paper_review_chat_followup_evidence_missing",
        "closed_paper_review_chat_responses_exchange_missing",
        "closed_paper_review_chat_followup_context_missing",
        "closed_paper_review_chat_order_state_changed",
    })
    ALLOWED_AI_CAUSES = frozenset({
        "local_rate_limit", "configuration", "rate_limit", "quota",
        "authentication", "model", "timeout", "connection", "provider",
    })

    def __init__(self, phase: str, cause: Exception):
        super().__init__("closed_paper_review_chat_phase_failed")
        self.phase = phase if phase in self.ALLOWED_PHASES else "unknown"
        code = str(cause)
        if code in self.ALLOWED_CAUSES:
            self.cause_code = code
        elif code.startswith("closed_paper_review_ai_unavailable:"):
            suffix = code.partition(":")[2]
            self.cause_code = (
                f"closed_paper_review_ai_unavailable:{suffix}"
                if suffix in self.ALLOWED_AI_CAUSES else "other"
            )
        elif code.startswith("closed_paper_review_dossier_incomplete:"):
            self.cause_code = "closed_paper_review_dossier_incomplete"
        else:
            self.cause_code = "other"


def _bounded_review_read_diagnostic(state: dict) -> dict[str, object]:
    """Summarize the private Responses checkpoint without exporting its facts."""
    exchange = state.get("responses_exchange") or {}
    progress = state.get("responses_progress") or {}
    trace = exchange.get("tool_trace") or progress.get("tool_trace") or []
    call = next((item for item in reversed(trace) if isinstance(item, dict)
                 and item.get("name") == "get_closed_trade_review"), None)
    result = (call or {}).get("result") or {}
    review = next((item for item in result.get("results") or []
                   if isinstance(item, dict) and item.get("scope") == "read_review_history"), None)
    allowed_statuses = {"completed", "partial", "unavailable", "error", "failed"}
    allowed_reasons = {"tool_internal_error", "tool_timeout", "source_unavailable",
                       "review_not_found", "tool_execution_failed"}
    call_status = (call or {}).get("status")
    read_status = (review or {}).get("status")
    read_reason = (review or {}).get("reason")
    return {
        "exchange_checkpoint": bool(exchange.get("response_id")),
        "progress_checkpoint": bool(progress.get("response_id")),
        "review_tool_seen": call is not None,
        "review_tool_status": (call_status if isinstance(call_status, str) and call_status in allowed_statuses else "other")
        if call else "missing",
        "review_read_status": (read_status if isinstance(read_status, str) and read_status in allowed_statuses else "other")
        if review else "missing",
        "review_read_reason": (read_reason if isinstance(read_reason, str) and read_reason in allowed_reasons else "other")
        if read_reason else "none",
    }


async def _review_read_diagnostic(user_id: int, run_id: str, conversation_id: str) -> dict[str, object]:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import (
        FinnV2RuntimeContractRepository,
    )

    try:
        async with async_session_factory() as session:
            contract = await FinnV2RuntimeContractRepository(session).get_for_run(run_id=run_id)
            if contract is None or contract.user_id != user_id or contract.conversation_id != conversation_id:
                return {}
            return _bounded_review_read_diagnostic(contract.state_json or {})
    except Exception:
        # This is optional diagnostics after a terminal failure. Preserve the
        # original failure if the diagnostic read cannot reach the database.
        return {}


@contextmanager
def _fixture_review_rollout(user_id: int):
    """Limit this runner process's review jobs to its inactive fixture owner."""
    keys = ("FINN_TRADE_REVIEW_ROLLOUT", "FINN_TRADE_REVIEW_USER_IDS")
    previous = {key: os.environ.get(key) for key in keys}
    try:
        os.environ["FINN_TRADE_REVIEW_ROLLOUT"] = "allowlist"
        os.environ["FINN_TRADE_REVIEW_USER_IDS"] = str(user_id)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _process_review_for_fixture(user_id: int) -> None:
    """Run the production projection/analysis jobs for just this QA owner.

    The regular workers use the deployed rollout allowlist and cannot see a
    newly created inactive fixture child. Calling their actual task bodies
    here avoids treating a one-minute beat delay as a product failure while
    keeping the production workers' rollout unchanged.
    """
    from backend.celery_task.finn_trade_review_task import (
        analyze_pending_trade_reviews, project_dirty_trade_reviews,
    )

    with _fixture_review_rollout(user_id):
        if project_dirty_trade_reviews.run() != 1:
            raise RuntimeError("closed_paper_review_projection_failed")
        with _capture_fixture_ai_errors() as ai_errors:
            analyzed = analyze_pending_trade_reviews.run()
        if ai_errors:
            raise RuntimeError("closed_paper_review_ai_unavailable:" + ai_errors[0])
        if analyzed != 1:
            raise RuntimeError("closed_paper_review_analysis_failed")


def _dossier_incomplete_fields(detail: dict) -> list[str]:
    """Name failed QA checks without disclosing the fixture's trade contents."""
    failed = []
    if detail.get("execution_environment") != "paper":
        failed.append("execution_environment")
    if len(detail.get("fills") or []) != 2:
        failed.append("fill_count")
    if detail.get("entry_qty") is None:
        failed.append("entry_qty")
    if detail.get("pnl_eur_before_fees") is None:
        failed.append("pnl_eur_before_fees")
    status = str(detail.get("analysis_status") or "missing")
    if status != "ready":
        known = {"pending", "running", "failed", "unavailable", "missing"}
        failed.append(f"analysis_status_{status if status in known else 'unknown'}")
    if not detail.get("analysis_json"):
        failed.append("analysis_json")
    return failed


@contextmanager
def _controlled_fixture_paper_quote():
    """Supply only this inactive Paper fixture with a deterministic EUR quote.

    The review probe tests ledger-to-dossier projection, not live market quote
    ingestion. This process-local override is restored before any review read
    or AI task and never changes application workers or market data.
    """
    if os.getenv("FINN_QA_ALLOW_CLOSED_PAPER_REVIEW_FIXTURE") != "1":
        raise RuntimeError("closed_paper_review_fixture_not_authorized")
    from backend.engine import trading_bot_execution as execution

    original = execution._get_live_price

    def paper_quote(conn, symbol: str, max_age_seconds=None):
        if str(symbol).upper() == fixture.SYMBOL and max_age_seconds is None:
            return float(fixture.PRICE_EUR)
        return original(conn, symbol, max_age_seconds)

    try:
        execution._get_live_price = paper_quote
        yield
    finally:
        execution._get_live_price = original


def _safe_ai_error_category(error: object) -> str:
    """Reduce provider/configuration failures to a fixed non-sensitive code."""
    value = str(error or "").casefold()
    if value == "ai_rate_limited":
        return "local_rate_limit"
    if "ai_unavailable_configuration" in value or "api key" in value or "api_key" in value:
        return "configuration"
    if "ai_rate_limited" in value or "429" in value or "rate limit" in value:
        return "rate_limit"
    if "quota" in value or "budget" in value:
        return "quota"
    if "authentication" in value or "401" in value:
        return "authentication"
    if "model" in value and ("not found" in value or "does not exist" in value):
        return "model"
    if "timeout" in value or "timed out" in value:
        return "timeout"
    if "connection" in value or "network" in value:
        return "connection"
    return "provider"


@contextmanager
def _capture_fixture_ai_errors():
    """Observe only safe error categories during this QA process's analysis."""
    from backend.utils import openai_client

    original = openai_client.ask_gpt_json_async
    categories: list[str] = []

    async def capture(*args, **kwargs):
        result = await original(*args, **kwargs)
        if isinstance(result, dict) and result.get("error"):
            categories.append(_safe_ai_error_category(result["error"]))
        return result

    try:
        openai_client.ask_gpt_json_async = capture
        yield categories
    finally:
        openai_client.ask_gpt_json_async = original


def _close_paper_position(user_id: int, bot_id: int, buy_decision_id: int) -> None:
    from backend.engine.trading_bot_execution import _auto_execute_decision, _persist_bot_order

    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT p.position_qty,o.execution_environment,o.status
                   FROM bot_portfolios p JOIN bot_orders o ON o.bot_id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND o.decision_id=%s
                     AND p.symbol='BTC'""",
                (user_id, bot_id, buy_decision_id),
            )
            opened = cur.fetchone()
            if not opened or opened[1:] != ("paper", "filled") or float(opened[0]) <= 0:
                raise RuntimeError("closed_paper_open_fill_missing")
            qty = float(opened[0])
            cur.execute(
                """SELECT strategy_id,setup_id FROM bot_decisions
                   WHERE id=%s AND user_id=%s AND bot_id=%s""",
                (buy_decision_id, user_id, bot_id),
            )
            strategy_id, setup_id = cur.fetchone()
            cur.execute(
                """INSERT INTO bot_decisions
                   (user_id,bot_id,strategy_id,setup_id,symbol,decision_date,
                    action,confidence,amount_eur,status,scores_json)
                   VALUES (%s,%s,%s,%s,'BTC',%s,'sell','high',50,'planned','{}'::jsonb)
                   RETURNING id""",
                (user_id, bot_id, strategy_id, setup_id, date.today()),
            )
            sell_decision_id = int(cur.fetchone()[0])
        # A Paper sell uses a verified current EUR quote; the recorded quantity
        # is exactly the amount opened by the preceding Paper buy.
        order = {"symbol": "BTC", "side": "sell", "quote_amount_eur": 50,
                 "estimated_price": fixture.PRICE_EUR, "estimated_qty": qty}
        _persist_bot_order(conn=conn, user_id=user_id, bot_id=bot_id,
                           decision_id=sell_decision_id, order=order, is_live=False)
        if _auto_execute_decision(conn=conn, user_id=user_id, bot_id=bot_id,
                                  decision_id=sell_decision_id, order=order,
                                  is_live=False, mode="auto") != "filled":
            raise RuntimeError("closed_paper_sell_not_filled")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _read_review(user_id: int) -> tuple[dict, int]:
    from backend.infrastructure.database import async_session_factory, engine
    from backend.services.finn_trade_review_service import FinnTradeReviewService

    try:
        async with async_session_factory() as session:
            reviews = FinnTradeReviewService(session)
            listing = await reviews.list_reviews(user_id, limit=10)
            items = listing.get("items") or []
            if not items:
                raise RuntimeError("closed_paper_review_missing")
            if len(items) != 1:
                raise RuntimeError("closed_paper_review_duplicate")
            review_id = int(items[0]["id"])
            detail = await reviews.get_review(user_id, review_id)
            incomplete_fields = _dossier_incomplete_fields(detail)
            if incomplete_fields:
                raise RuntimeError("closed_paper_review_dossier_incomplete:" + ",".join(incomplete_fields))
            await reviews.set_lesson(user_id, review_id, "Ik controleer mijn exitplan na iedere Paper-trade.")
            reread = await reviews.get_review(user_id, review_id)
            lesson = reread.get("lesson") or {}
            if (lesson.get("status") != "active"
                    or lesson.get("lesson_text") != "Ik controleer mijn exitplan na iedere Paper-trade."):
                raise RuntimeError("closed_paper_lesson_not_readable")
            return {"result": "PASS", "environment": "paper",
                    "closed_positions": 1, "fills": 2,
                    "dossier_readable": True, "lesson_confirmed_and_readable": True}, review_id
    finally:
        await engine.dispose()


async def _chat_turn(user_id: int, message: str, *, conversation_id: str | None = None):
    """Run the real FINN worker body for the rollout-isolated fixture owner."""
    from backend.celery_task.finn_v2_task import _process_finn_v2_run
    from backend.infrastructure.database import async_session_factory
    from backend.schemas.finn_v2_schema import AgentRunRequest
    from backend.services.finn_v2_gateway_service import FinnV2GatewayService

    request_id = f"finn-qa-review-{uuid.uuid4().hex}"
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        run = await gateway.create_run(
            user_id=user_id,
            request=AgentRunRequest(message=message, conversation_id=conversation_id,
                                    transport="chat", client_context={"surface": "qa_closed_paper_review"}),
            request_path="/api/assistant/chat", request_id=request_id,
            trace_id=f"finn-qa-review-trace-{uuid.uuid4().hex}",
        )
        run_id = run.id
        await session.commit()
    # The production worker's own rollout does not include this new inactive
    # child user. Run the same task body within this bounded QA process, as the
    # existing projection/analysis probe does, rather than changing rollout.
    await _process_finn_v2_run(run_id=run_id, owner=f"qa-review:{uuid.uuid4().hex}")
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        persisted = await gateway.get_run(run_id=run_id, user_id=user_id)
        return await gateway.run_service.envelope_from_run(persisted)


async def _has_responses_exchange(user_id: int, run_id: str, conversation_id: str) -> bool:
    """Check the owner-bound Responses exchange for this exact chat turn."""
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_runtime_contract_repository import (
        FinnV2RuntimeContractRepository,
    )

    async with async_session_factory() as session:
        contract = await FinnV2RuntimeContractRepository(session).get_for_run(run_id=run_id)
        if contract is None or contract.user_id != user_id or contract.conversation_id != conversation_id:
            return False
        exchange = (contract.state_json or {}).get("responses_exchange") or {}
        return bool(exchange.get("response_id") and exchange.get("answer"))


async def _read_review_in_chat(user_id: int, review_id: int) -> dict:
    """Require a substantive read-only chat answer and a contextual follow-up."""
    from backend.infrastructure.database import engine

    try:
        first = await _chat_turn(
            user_id,
            "Wat weet je over mijn laatst afgesloten Paper-trade en de les die ik "
            "daarbij heb bevestigd? Alleen teruglezen; geen voorstel of actie.",
        )
        response = first.response
        if first.status != "completed" or response is None:
            failure = ClosedPaperChatTurnFailure("first_turn", first)
            failure.review_read_diagnostic = await _review_read_diagnostic(
                user_id, first.run_id, first.conversation_id,
            )
            raise failure
        if (response.proposal_id or response.confirmation_required
                or (first.policy and first.policy.execute_allowed)):
            raise RuntimeError("closed_paper_review_chat_unexpected_action")
        if not any(item.entity_type == "review_history" for item in response.evidence):
            raise RuntimeError("closed_paper_review_chat_evidence_missing")
        if "exitplan" not in response.content.casefold():
            raise RuntimeError("closed_paper_review_chat_lesson_missing")

        second = await _chat_turn(
            user_id,
            "Wat kan ik van deze bevestigde les leren? Herhaal de les en zeg "
            "of mijn oorspronkelijke plan is vastgelegd. Alleen sparren.",
            conversation_id=first.conversation_id,
        )
        response = second.response
        if second.status != "completed" or response is None:
            failure = ClosedPaperChatTurnFailure("followup", second)
            failure.review_read_diagnostic = await _review_read_diagnostic(
                user_id, second.run_id, second.conversation_id,
            )
            raise failure
        if (second.conversation_id != first.conversation_id or response.proposal_id
                or response.confirmation_required or (second.policy and second.policy.execute_allowed)):
            raise RuntimeError("closed_paper_review_chat_followup_context_or_action")
        if not any(item.entity_type == "review_history" for item in response.evidence):
            raise RuntimeError("closed_paper_review_chat_followup_evidence_missing")
        if not await _has_responses_exchange(user_id, second.run_id, second.conversation_id):
            raise RuntimeError("closed_paper_review_chat_responses_exchange_missing")
        followup = response.content.casefold()
        if ("exitplan" not in followup or "plan" not in followup
                or not any(term in followup for term in ("niet", "onbekend", "ontbreekt"))):
            raise RuntimeError("closed_paper_review_chat_followup_context_missing")
        return {"result": "PASS", "turns": 2, "owner_scoped_review_evidence": True,
                "confirmed_lesson_readable": True, "followup_same_conversation": True,
                "action_proposals": 0, "dispatch_mode": "in_process_production_task_body"}
    finally:
        await engine.dispose()


def _assert_fixture_orders_unchanged(user_id: int, bot_id: int) -> None:
    """The two deliberate Paper fills must be the only orders after chat."""
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*), COUNT(*) FILTER (
                       WHERE execution_environment IS DISTINCT FROM 'paper'
                          OR status IS DISTINCT FROM 'filled')
                   FROM bot_orders WHERE user_id=%s AND bot_id=%s""",
                (user_id, bot_id),
            )
            total, unexpected = cur.fetchone()
        if int(total) != 2 or int(unexpected) != 0:
            raise RuntimeError("closed_paper_review_chat_order_state_changed")
    finally:
        conn.close()


def run(namespace: str, *, include_chat: bool = False,
        on_execution_attempt: Callable[[], None] | None = None) -> dict:
    if os.getenv("FINN_QA_ALLOW_CLOSED_PAPER_REVIEW_FIXTURE") != "1":
        raise RuntimeError("closed_paper_review_fixture_not_authorized")
    user_id = bot_id = None
    phase = "binding"
    try:
        bound = fixture._require_protected_run(namespace)
        phase = "seed"
        user_id, bot_id, buy_decision_id = fixture._seed(namespace, bound)
        phase = "prepare_entry"
        conn = fixture._connection()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE bot_decisions SET decision_date=%s
                       WHERE id=%s AND user_id=%s AND bot_id=%s AND status='planned'""",
                    (date.today() - timedelta(days=1), buy_decision_id, user_id, bot_id),
                )
                if cur.rowcount != 1:
                    raise RuntimeError("closed_paper_entry_decision_missing")
            conn.commit()
        finally:
            conn.close()
        with _controlled_fixture_paper_quote():
            phase = "paper_buy"
            if on_execution_attempt is not None:
                on_execution_attempt()
            fixture._execute(user_id, bot_id, buy_decision_id)
            phase = "paper_sell"
            if on_execution_attempt is not None:
                on_execution_attempt()
            _close_paper_position(user_id, bot_id, buy_decision_id)
        phase = "analysis"
        _process_review_for_fixture(user_id)
        phase = "dossier"
        result, review_id = asyncio.run(_read_review(user_id))
        if include_chat:
            phase = "chat"
            with _fixture_review_rollout(user_id):
                result["finn_chat"] = asyncio.run(_read_review_in_chat(user_id, review_id))
            phase = "orders"
            _assert_fixture_orders_unchanged(user_id, bot_id)
        return result
    except Exception as error:
        if include_chat and not isinstance(error, ClosedPaperChatTurnFailure):
            raise ClosedPaperProbeStageFailure(phase, error) from None
        raise
    finally:
        if user_id is not None and bot_id is not None:
            # Preserve this bounded synthetic evidence, but make execution
            # impossible even if dossier projection or readback fails.
            try:
                fixture._finish(namespace, user_id, bot_id, passed=False)
            except Exception as error:
                # Disabling the synthetic owner/bot takes priority over the
                # earlier product failure: never hide a failed cleanup.
                if include_chat:
                    raise ClosedPaperProbeStageFailure("cleanup", error) from None
                raise
