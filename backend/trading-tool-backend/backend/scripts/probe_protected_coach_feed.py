"""Bounded FINN coach-feed acceptance on inactive, owner-marked QA children.

The probe never writes shared quotes, ordinary users, broker credentials or
Live orders. A process-local move threshold exercises the plan observer when
the real ETH quote has a small, fresh movement; the production threshold is
covered separately by unit tests and is not claimed by this live probe.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timedelta, timezone

from backend.scripts import probe_protected_portfolio_paper_fx as paper
from backend.scripts import probe_protected_score2_stale_paper as score


SAFE_FAILURES = frozenset({
    "coach_feed_fixture_not_authorized", "coach_feed_manifest_forbidden",
    "coach_feed_source_unavailable", "coach_feed_source_not_moving",
    "coach_feed_score_missing", "coach_feed_plan_card_missing",
    "coach_feed_improvement_card_missing", "coach_feed_risk_card_missing",
    "coach_feed_owner_scope_failed", "coach_feed_detail_failed",
    "coach_feed_discuss_failed", "coach_feed_unexpected_order", "coach_feed_cleanup_failed",
    "coach_feed_quarantine_failed", "coach_feed_runtime_failed",
})
SOURCE_LIMITATIONS = frozenset({"coach_feed_source_unavailable", "coach_feed_source_not_moving"})
TASK_STATES = {
    "PENDING": "pending_unconfirmed", "RECEIVED": "received",
    "STARTED": "started", "SUCCESS": "success", "FAILURE": "failure",
    "RETRY": "retry", "REVOKED": "revoked",
}


def _safe_task_status(task) -> str:
    try:
        return TASK_STATES.get(task.state, "unknown")
    except Exception:
        return "unknown"


def _require_run(namespace: str) -> int:
    if (os.getenv("FINN_QA_ALLOW_COACH_FEED_FIXTURE") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"):
        raise RuntimeError("coach_feed_fixture_not_authorized")
    if not score.NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("coach_feed_fixture_not_authorized")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("coach_feed_fixture_not_authorized")
    return int(bound)


def _counts(user_id: int) -> tuple[int, int, int, int]:
    connection = score._connection()
    try:
        with connection.cursor() as cursor:
            values = []
            for table in ("bot_orders", "bot_executions", "exchange_keys", "finn_v2_proposals"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                values.append(int(cursor.fetchone()[0]))
        return tuple(values)
    finally:
        connection.close()


async def _feed(user_id: int, expected: str, *, subject: str | None = None) -> dict:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async with async_session_factory() as session:
        feed = FinnCoachFeedService(session)
        rows = await feed.list(user_id=user_id)
        selected = [row for row in rows if row.get("event_type") == expected
                    and (subject is None or row.get("subject_type") == subject)]
        if len(selected) != 1:
            raise RuntimeError({
                "plan_review": "coach_feed_plan_card_missing",
                "improvement_suggestion": "coach_feed_improvement_card_missing",
                "position_risk": "coach_feed_risk_card_missing",
            }[expected])
        row = selected[0]
        detail = await feed.detail(user_id=user_id, item_id=str(row["id"]))
        if not detail or detail.get("event_type") != expected:
            raise RuntimeError("coach_feed_detail_failed")
        other = await feed.detail(user_id=user_id + 1, item_id=str(row["id"]))
        if other is not None:
            raise RuntimeError("coach_feed_owner_scope_failed")
        return {"id": str(row["id"]), "evidence": detail.get("evidence") or {},
                "status": detail.get("status")}


async def _await_feed(user_id: int, expected: str, *, subject: str | None = None,
                      timeout_seconds: float = 45, task=None,
                      diagnostic: dict | None = None) -> dict:
    deadline = time.monotonic() + timeout_seconds
    while True:
        if diagnostic is not None:
            diagnostic["task_status"] = _safe_task_status(task)
        try:
            card = await _feed(user_id, expected, subject=subject)
            if diagnostic is not None:
                diagnostic["card_found"] = True
                diagnostic["task_status"] = _safe_task_status(task)
            return card
        except RuntimeError as error:
            timed_out = time.monotonic() >= deadline
            if diagnostic is not None:
                diagnostic["timed_out"] = timed_out
                diagnostic["task_status"] = _safe_task_status(task)
            if str(error) != {
                "improvement_suggestion": "coach_feed_improvement_card_missing",
                "position_risk": "coach_feed_risk_card_missing",
            }.get(expected) or timed_out:
                raise
            await asyncio.sleep(2)


def _verified_plan_evidence(evidence: dict) -> bool:
    return bool(
        evidence.get("status") == "measured_move"
        and evidence.get("symbol") == "ETH"
        and evidence.get("source_status") == "available"
        and evidence.get("plan_status") == "matches"
        and evidence.get("quote_source_observed_at") is not None
    )


async def _discuss(user_id: int, item_id: str, *, symbol: str, question: str) -> dict:
    """Use the real FINN task body with the same selected-feed context as UI."""
    import uuid

    from backend.celery_task.finn_v2_task import _process_finn_v2_run
    from backend.infrastructure.database import async_session_factory
    from backend.schemas.finn_v2_schema import AgentRunRequest
    from backend.services.finn_v2_gateway_service import FinnV2GatewayService

    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        run = await gateway.create_run(
            user_id=user_id,
            request=AgentRunRequest(
                message=question, transport="chat",
                client_context={"surface": "qa_coach_feed", "feed_item_id": item_id},
            ),
            request_path="/api/assistant/chat",
            request_id=f"qa-coach-feed-{uuid.uuid4().hex}",
            trace_id=f"qa-coach-feed-trace-{uuid.uuid4().hex}",
        )
        await session.commit()
    await _process_finn_v2_run(run_id=run.id, owner=f"qa-coach-feed:{uuid.uuid4().hex}")
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        persisted = await gateway.get_run(run_id=run.id, user_id=user_id)
        turn = await gateway.run_service.envelope_from_run(persisted)
    response = turn.response
    if (turn.status != "completed" or response is None or response.proposal_id
            or response.confirmation_required or not response.content
            or symbol.casefold() not in response.content.casefold()):
        raise RuntimeError("coach_feed_discuss_failed")
    return {"completed": True, "named_subject": True,
            "read_only": True, "answer_length": len(response.content)}


async def _observe_score_feed(user_id: int, *, threshold: float, trace: dict) -> dict:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    # Only this isolated child's category weights become invalid. This proves
    # that a real configuration gap yields an advice card, not an automatic edit.
    trace["stage"] = "weights_invalid"
    connection = score._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE users SET ai_preferences=jsonb_set(ai_preferences,
                '{asset_benchmark_weights}',
                '{\"ETH\":{\"market\":0,\"macro\":0,\"technical\":0}}'::jsonb)
                WHERE id=%s AND is_active=FALSE AND ai_preferences->>'qa_fixture'=%s""",
                (user_id, score.FIXTURE_MARKER))
            if cursor.rowcount != 1:
                raise RuntimeError("coach_feed_owner_scope_failed")
        connection.commit()
    finally:
        connection.close()
    from backend.celery_task.store_daily_scores_task import reconcile_coach_feed_score
    trace["stage"] = "improvement_dispatch"
    task = reconcile_coach_feed_score.delay(user_id, "ETH")
    diagnostic = {"dispatch": "enqueued", "task_status": "unknown",
                  "card_found": False, "timed_out": False}
    trace["improvement_diagnostic"] = diagnostic
    trace["stage"] = "improvement_wait"
    improvement = await _await_feed(user_id, "improvement_suggestion", subject="asset",
                                   task=task, diagnostic=diagnostic)
    if improvement["evidence"].get("suggestion_kind") != "weights":
        raise RuntimeError("coach_feed_improvement_card_missing")
    trace["stage"] = "improvement_discuss"
    improvement_discuss = await _discuss(
        user_id, improvement["id"], symbol="ETH",
        question="Bespreek dit verbeteringsvoorstel voor ETH. Welke opgeslagen "
                 "benchmarkweging verdient controle? Wijzig niets.",
    )

    # Restore this child's original valid weights before evaluating its plan.
    # The improvement card remains a dated record of the preceding gap.
    trace["stage"] = "weights_restore"
    connection = score._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE users SET ai_preferences=ai_preferences-
                'asset_benchmark_weights' WHERE id=%s AND is_active=FALSE
                AND ai_preferences->>'qa_fixture'=%s""",
                (user_id, score.FIXTURE_MARKER))
            if cursor.rowcount != 1:
                raise RuntimeError("coach_feed_owner_scope_failed")
        connection.commit()
    finally:
        connection.close()

    trace["stage"] = "improvement_resolution"
    async with async_session_factory() as session:
        reopened = await FinnCoachFeedService(session).reconcile_improvement_suggestions(
            user_id=user_id, symbol="ETH")
        await session.commit()
    if reopened:
        raise RuntimeError("coach_feed_improvement_card_missing")
    try:
        await _feed(user_id, "improvement_suggestion", subject="asset")
    except RuntimeError as error:
        if str(error) != "coach_feed_improvement_card_missing":
            raise
    else:
        raise RuntimeError("coach_feed_improvement_card_missing")

    # Observe the move last: the normal-threshold worker above would resolve
    # a synthetic below-threshold plan card. The earlier improvement card is
    # now resolved because the test-only invalid weights were restored.
    trace["stage"] = "plan_observation"
    previous = os.environ.get("FINN_COACH_MOVE_THRESHOLD_PCT")
    os.environ["FINN_COACH_MOVE_THRESHOLD_PCT"] = str(threshold)
    try:
        async with async_session_factory() as session:
            observer = FinnCoachFeedService(session)
            plan = await observer.reconcile_plan_reviews(user_id=user_id, symbol="ETH")
            await session.commit()
    finally:
        if previous is None:
            os.environ.pop("FINN_COACH_MOVE_THRESHOLD_PCT", None)
        else:
            os.environ["FINN_COACH_MOVE_THRESHOLD_PCT"] = previous
    if len(plan) != 1:
        raise RuntimeError("coach_feed_plan_card_missing")
    trace["stage"] = "plan_readback"
    card = await _feed(user_id, "plan_review", subject="setup")
    evidence = card["evidence"]
    if not _verified_plan_evidence(evidence):
        raise RuntimeError("coach_feed_plan_card_missing")
    trace["stage"] = "plan_discuss"
    plan_discuss = await _discuss(
        user_id, card["id"], symbol="ETH",
        question="Bespreek deze planherbeoordeling. Welke gemeten beweging en "
                 "opgeslagen setup zijn relevant, en wat controleer ik nu? Wijzig niets.",
    )
    return {"plan_review": "passed", "improvement_suggestion": "passed",
            "plan_source_timestamp_present": True, "production_move_threshold_tested": False,
            "plan_dispatch_tested": False, "improvement_worker_dispatch_tested": True,
            "plan_discuss": plan_discuss, "improvement_discuss": improvement_discuss}


async def _fresh_eth_move() -> tuple[float, float, datetime]:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.market_data_repository import MarketDataRepository

    async with async_session_factory() as session:
        quote = await MarketDataRepository(session).get_latest_quoted_snapshot("ETH")
    observed = getattr(quote, "source_observed_at", None) if quote else None
    if observed is None:
        raise RuntimeError("coach_feed_source_unavailable")
    observed = observed.replace(tzinfo=timezone.utc) if observed.tzinfo is None else observed.astimezone(timezone.utc)
    if not timedelta(0) <= datetime.now(timezone.utc) - observed <= timedelta(minutes=60):
        raise RuntimeError("coach_feed_source_unavailable")
    try:
        change = float(quote.change_24h)
        movement = abs(change)
    except (TypeError, ValueError):
        raise RuntimeError("coach_feed_source_unavailable") from None
    if not 0 < movement < 10000:
        raise RuntimeError("coach_feed_source_not_moving")
    return movement, change, observed


def _align_child_market_reading(user_id: int, *, change: float, observed: datetime) -> None:
    """Copy the real quote's dated change only into this child's indicator."""
    connection = score._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""UPDATE market_data_indicators SET value=%s,
                source_observed_at=%s,timestamp=%s
                WHERE user_id=%s AND symbol='ETH' AND name='change_24h'
                  AND EXISTS (SELECT 1 FROM users WHERE id=%s AND is_active=FALSE
                    AND ai_preferences->>'qa_fixture'=%s)""",
                (change, observed, observed, user_id, user_id, score.FIXTURE_MARKER))
            if cursor.rowcount != 1:
                raise RuntimeError("coach_feed_owner_scope_failed")
        connection.commit()
    finally:
        connection.close()


def _score_case(namespace: str, bound: int, *, trace: dict, run_async) -> dict:
    user_id = bot_id = None
    passed = False
    try:
        trace["stage"] = "source"
        movement, change, observed = run_async(_fresh_eth_move())
        trace["stage"] = "seed"
        user_id, bot_id, _ = score._seed(namespace, bound, bot_active=False)
        trace["fixture_state"] = "created"
        trace["stage"] = "source_alignment"
        _align_child_market_reading(user_id, change=change, observed=observed)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
        trace["stage"] = "score_build"
        build_daily_scores_for_user(user_id, ["ETH"], publish_feed=False)
        trace["stage"] = "feed_observation"
        result = run_async(_observe_score_feed(user_id, threshold=min(movement / 2, 9.0),
                                               trace=trace))
        trace["stage"] = "safety_check"
        if _counts(user_id) != (0, 0, 0, 0):
            raise RuntimeError("coach_feed_unexpected_order")
        passed = True
        return result
    finally:
        if user_id is not None and bot_id is not None:
            try:
                if passed:
                    score._cleanup(namespace, user_id, bot_id, require_safe_pair_cleanup=True)
                    trace["fixture_state"] = "cleaned"
                else:
                    score._quarantine(namespace, user_id, bot_id)
                    trace["fixture_state"] = "quarantined"
            except Exception:
                trace["fixture_state"] = "cleanup_failed"
                raise RuntimeError("coach_feed_cleanup_failed" if passed else
                                   "coach_feed_quarantine_failed") from None


def _risk_case(namespace: str, bound: int, *, trace: dict, run_async) -> dict:
    user_id = bot_id = None
    passed = False
    try:
        trace["stage"] = "source"
        source = paper._verified_source_price_eur()
        trace["stage"] = "seed"
        user_id, bot_id, decision_id = paper._seed(namespace, bound)
        trace["fixture_state"] = "created"
        trace["stage"] = "paper_execution"
        trace["paper_execution_attempted"] = True
        paper._execute_and_replay(user_id, bot_id, decision_id, source["eur_price"])
        # The actual virtual Paper fill provides valuation and cash evidence.
        # Lower only the synthetic bot's saved exposure threshold afterwards.
        trace["stage"] = "risk_limit"
        connection = paper._connection()
        try:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE bot_configs SET max_asset_exposure_pct=10,
                    is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE""",
                    (bot_id, user_id))
                if cursor.rowcount != 1:
                    raise RuntimeError("coach_feed_owner_scope_failed")
            connection.commit()
        finally:
            connection.close()
        from backend.celery_task.portfolio_snapshot_task import reconcile_paper_position_risk
        trace["stage"] = "worker_dispatch"
        reconcile_paper_position_risk.delay(user_id)
        trace["stage"] = "feed_observation"
        card = run_async(_await_feed(user_id, "position_risk", subject="bot"))
        if card["evidence"].get("status") != "above_saved_limit":
            raise RuntimeError("coach_feed_risk_card_missing")
        trace["stage"] = "discuss"
        discussed = run_async(_discuss(
            user_id, card["id"], symbol="BTC",
            question="Bespreek dit positierisico voor mijn BTC Paper-bot. "
                     "Welke opgeslagen limiet is overschreden en wat controleer ik? "
                     "Wijzig niets en plaats geen order.",
        ))
        trace["stage"] = "safety_check"
        if _counts(user_id) != (1, 1, 0, 0):
            raise RuntimeError("coach_feed_unexpected_order")
        passed = True
        return {"position_risk": "passed", "paper_only": True,
                "risk_worker_dispatch_tested": True,
                "valuation_source_timestamp_present": bool(card["evidence"].get("valuation_as_of")),
                "risk_discuss": discussed}
    finally:
        if user_id is not None and bot_id is not None:
            try:
                paper._finish(namespace, user_id, bot_id, passed=passed)
                trace["fixture_state"] = "cleaned" if passed else "quarantined"
            except Exception:
                trace["fixture_state"] = "cleanup_failed"
                raise RuntimeError("coach_feed_cleanup_failed") from None


def run(namespace: str) -> dict:
    bound = _require_run(namespace)
    # Both cases run even when the other fails; only fixed failure codes leave
    # the protected host. A failed child is quarantined for QA diagnosis.
    from backend.scripts.probe_protected_paper_exit_reconciliation import _guard_live_exchange

    results = {}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with _guard_live_exchange() as live_attempts:
            for name, procedure in (("score_and_plan", _score_case), ("paper_risk", _risk_case)):
                trace = {"stage": "preflight", "fixture_state": "not_created",
                         "paper_execution_attempted": False}
                try:
                    results[name] = procedure(namespace, bound, trace=trace,
                                              run_async=loop.run_until_complete)
                    results[name]["fixture_state"] = trace["fixture_state"]
                except Exception as error:
                    code = str(error)
                    results[name] = {"result": "FAIL", "reason": code if code in SAFE_FAILURES
                                     else "coach_feed_runtime_failed",
                                     "failure_stage": trace["stage"],
                                     "fixture_state": trace["fixture_state"]}
                if name == "score_and_plan" and "improvement_diagnostic" in trace:
                    diagnostic = trace["improvement_diagnostic"]
                    status = diagnostic.get("task_status")
                    results[name]["improvement_diagnostic"] = {
                        "dispatch": "enqueued" if diagnostic.get("dispatch") == "enqueued" else "unknown",
                        "task_status": status if status in TASK_STATES.values() else "unknown",
                        "card_found": diagnostic.get("card_found") is True,
                        "timed_out": diagnostic.get("timed_out") is True,
                    }
                if name == "paper_risk":
                    results["paper_execution_attempts"] = int(trace["paper_execution_attempted"])
        from backend.infrastructure.database import engine

        try:
            loop.run_until_complete(engine.dispose())
        except Exception:
            results["resource_cleanup"] = {"result": "FAIL", "reason": "coach_feed_runtime_failed"}
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()
    results["live_calls"] = len(live_attempts)
    if live_attempts:
        results["safety"] = {"result": "FAIL", "reason": "coach_feed_unexpected_order"}
    failures = [item.get("reason") for item in results.values()
                if isinstance(item, dict) and item.get("result") == "FAIL"]
    results["result"] = ("PASS" if not failures else
                         "INCONCLUSIVE" if all(reason in SOURCE_LIMITATIONS for reason in failures)
                         else "FAIL")
    return results
