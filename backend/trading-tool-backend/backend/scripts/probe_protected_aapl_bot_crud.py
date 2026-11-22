"""One-shot AAPL manual Paper bot CRUD on an inactive protected child.

No bot worker, manual execution, Paper funding, or broker API is called.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid
from datetime import datetime, timezone

from backend.scripts import probe_protected_score2_stale_paper as fixture


MARKER = "finn_aapl_bot_crud_qa_v1"
FAILURES = frozenset({
    "aapl_bot_not_authorized", "aapl_bot_owner_unsafe", "aapl_bot_seed_unsafe",
    "aapl_bot_proposal_missing", "aapl_bot_proposal_unsafe",
    "aapl_bot_confirmation_failed", "aapl_bot_replay_failed",
    "aapl_bot_postcondition_failed", "aapl_bot_cleanup_failed",
    "aapl_bot_runtime_failed",
})
TRADE_TABLES = ("bot_trade_plans", "bot_orders", "bot_executions",
                "bot_ledger", "bot_decisions")
DELETE_TABLES = (
    "bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
    "bot_decisions", "portfolio_value_snapshots_v2", "bot_portfolio_snapshots",
    "portfolio_balance_snapshots", "bot_portfolios", "bot_configs",
    "strategies", "setups", "daily_scores", "daily_reports",
    "finn_coach_feed_items", "watchlists", "macro_data",
    "technical_indicators", "market_data_indicators", "user_indicator_configs",
)
PROPOSAL_STATUSES = frozenset({
    "completed", "clarification_required", "unavailable", "failed",
    "blocked", "rejected", "downgraded", "canceled",
})
PROPOSAL_MODES = frozenset({
    "CAPABILITY", "READ", "EVALUATE", "CREATE_PROPOSAL", "ACTION_PROPOSAL",
    "CLARIFICATION", "CONFIRMATION", "EXECUTION", "UNAVAILABLE",
})
PROPOSAL_SLOTS = frozenset({
    "strategy_id", "name", "budget_total_eur", "paper_initial_cash_eur",
    "mode", "symbol", "asset", "quote_currency",
})
PROPOSAL_ERRORS = frozenset({
    "selector_phase_timeout", "lifecycle_deadline_exceeded", "orchestrator_failed",
    "responses_provider_quota_unavailable", "responses_provider_unconfigured",
    "responses_provider_timeout", "responses_provider_error",
    "responses_context_length_exceeded", "responses_lifecycle_budget_exhausted",
    "responses_tool_round_limit", "responses_tool_call_limit",
    "responses_incomplete", "responses_empty_answer",
    "guided_proposal_tool_call_required", "guided_turn_continuation_unverified",
    "proposal_tool_validation_failed", "responses_tool_execution_failed",
    "runtime_contract_terminal_projection_missing", "responses_evidence_not_verified",
    "no_evidence_available", "source_unavailable", "turn_contract_mismatch",
})


def _proposal_diagnostic(status: object, error_code: object, projection: object) -> dict:
    data = projection if isinstance(projection, dict) else {}
    draft = data.get("action_draft") or {}
    if not isinstance(draft, dict):
        draft = {}
    raw_missing = data.get("missing_inputs") or draft.get("missing_inputs") or []
    if not isinstance(raw_missing, (list, tuple)):
        raw_missing = []
    operation = data.get("final_operation_id") or data.get("initial_operation_id")
    guided = draft.get("operation_id")
    requested = draft.get("next_missing_input")
    mode = data.get("final_mode")
    response_type = data.get("terminal_response_type")
    def allowed(value: object, choices: frozenset[str] | set[str]) -> bool:
        return isinstance(value, str) and value in choices

    return {
        "status": status if allowed(status, PROPOSAL_STATUSES) else "other",
        "error_category": error_code if allowed(error_code, PROPOSAL_ERRORS) else ("none" if not error_code else "other"),
        "answer_mode": mode if allowed(mode, PROPOSAL_MODES) else ("none" if not mode else "other"),
        "response_type": response_type if allowed(response_type, {"response", "failure"}) else "other",
        "operation": operation if operation == "create_bot" else ("none" if not operation else "other"),
        "guided_operation": guided if guided == "create_bot" else ("none" if not guided else "other"),
        "missing_inputs": sorted({slot for slot in raw_missing[:8] if allowed(slot, PROPOSAL_SLOTS)}),
        "requested_slot": requested if allowed(requested, PROPOSAL_SLOTS) else ("none" if not requested else "other"),
        "dispatch_count": data.get("dispatch_count") if type(data.get("dispatch_count")) is int and data.get("dispatch_count") in (0, 1, 2) else "other",
        "attempt_count": data.get("attempt_count") if type(data.get("attempt_count")) is int and data.get("attempt_count") in (0, 1, 2) else "other",
    }


def _strategy_read_status(rows: object) -> str:
    if not isinstance(rows, (list, tuple)):
        return "unknown"
    matching = [row for row in rows if isinstance(row, (list, tuple)) and len(row) == 3
                and isinstance(row[0], str)
                and row[0] in {"read_linked_strategy", "read_linked_strategies"}]
    if not matching:
        return "not_requested"
    if any(row[1] == "completed" and row[2] is True for row in matching):
        return "available"
    if any(row[1] == "failed" or row[2] is False for row in matching):
        return "failed"
    return "requested_not_completed"


def _bound_owner(namespace: str) -> int:
    if (not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
            or os.getenv("FINN_QA_ALLOW_AAPL_BOT_CRUD") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"):
        raise RuntimeError("aapl_bot_not_authorized")
    value = os.getenv("FINN_QA_USER_ID", "")
    if not value.isdecimal() or int(value) <= 0:
        raise RuntimeError("aapl_bot_not_authorized")
    return int(value)


def _names(namespace: str) -> tuple[str, str, str]:
    return (f"QA AAPL Setup {namespace}", f"QA AAPL Strategy {namespace}",
            f"QA AAPL Bot {namespace}")


def _seed(namespace: str, owner: int) -> tuple[int, int]:
    from backend.utils.auth_utils import hash_password

    setup_name, strategy_name, _ = _names(namespace)
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (owner,))
            parent = cursor.fetchone()
            if (not parent or parent[0] != "user" or parent[1] is not True
                    or (parent[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER):
                raise RuntimeError("aapl_bot_owner_unsafe")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (owner,))
            if cursor.fetchone()[0]:
                raise RuntimeError("aapl_bot_owner_unsafe")
            cursor.execute(
                """INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                   VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (f"aapl-bot-{namespace}@tradamind.example",
                 hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": MARKER, "qa_namespace": namespace})),
            )
            user_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO setups
                   (user_id,name,symbol,timeframe,setup_type,created_at,last_validated)
                   VALUES (%s,%s,'AAPL','1D','trade',%s,%s) RETURNING id""",
                (user_id, setup_name, now, now),
            )
            setup_id = int(cursor.fetchone()[0])
            cursor.execute(
                """INSERT INTO strategies
                   (user_id,setup_id,name,symbol,timeframe,setup_type,execution_mode,
                    base_amount,entry,stop_loss,targets,data,created_at)
                   VALUES (%s,%s,%s,'AAPL','1D','trade','fixed',10,250,240,
                           ARRAY[270]::NUMERIC[],%s::jsonb,%s) RETURNING id""",
                (user_id, setup_id, strategy_name,
                 json.dumps({"price_currency": "USD", "price_currency_confirmed": True}), now),
            )
            strategy_id = int(cursor.fetchone()[0])
        connection.commit()
        return user_id, strategy_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _snapshot(user_id: int, namespace: str) -> dict:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE",
                (user_id,),
            )
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("aapl_bot_owner_unsafe")
            counts = {}
            for table in (*TRADE_TABLES, "bot_portfolios", "bot_configs", "exchange_keys"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                counts[table] = int(cursor.fetchone()[0])
            return counts
    finally:
        connection.close()


async def _proposal(user_id: int, strategy_name: str, bot_name: str) -> dict:
    from backend.celery_task.finn_v2_task import _process_finn_v2_run
    from backend.infrastructure.database import async_session_factory
    from backend.schemas.finn_v2_schema import AgentRunRequest
    from backend.services.finn_v2_gateway_service import FinnV2GatewayService
    from sqlalchemy import text

    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        run = await gateway.create_run(
            user_id=user_id,
            request=AgentRunRequest(
                message=(f"Maak een handmatige Paper-botconfiguratie met naam {bot_name} "
                         f"voor mijn bestaande AAPL-strategie {strategy_name}. "
                         "Totaalbudget 10 euro en Paper-startkapitaal 0 euro. "
                         "Toon eerst een voorstel; plaats geen order en activeer geen live trading."),
                transport="chat", workspace_hints={"symbol": "AAPL"},
                client_context={"surface": "qa_aapl_bot_crud"},
            ),
            request_path="/api/assistant/chat",
            request_id=f"qa-aapl-bot-{uuid.uuid4().hex}",
        )
        run_id = run.id
        await session.commit()
    await asyncio.wait_for(
        _process_finn_v2_run(run_id=run_id, owner=f"qa-aapl-bot:{uuid.uuid4().hex}"),
        timeout=90,
    )
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        saved = await gateway.get_run(run_id=run_id, user_id=user_id)
        envelope = await gateway.run_service.envelope_from_run(saved)
        response = envelope.response
        projection_row = await session.execute(text("""SELECT terminal_projection_json
            FROM finn_v2_runtime_contracts
            WHERE run_id=:run_id AND user_id=:user_id"""),
            {"run_id": run_id, "user_id": user_id})
        tool_rows = await session.execute(text("""SELECT tool_name,status,success
            FROM finn_v2_tool_calls WHERE run_id=:run_id AND user_id=:user_id
            AND tool_name IN ('read_linked_strategy','read_linked_strategies')"""),
            {"run_id": run_id, "user_id": user_id})
        diagnostic = _proposal_diagnostic(
            envelope.status, envelope.error_code, projection_row.scalar_one_or_none(),
        )
        diagnostic["strategy_read"] = _strategy_read_status(tool_rows.all())
        return {"status": envelope.status,
                "proposal_id": response.proposal_id if response else None,
                "confirmation_required": bool(response and response.confirmation_required),
                "diagnostic": diagnostic}


def _safe_bot_fields(fields: object, *, strategy_id: int, bot_name: str) -> bool:
    if not isinstance(fields, dict):
        return False
    from backend.schemas.bot_schema import BotConfigCreateSchema

    try:
        bot = BotConfigCreateSchema.parse_obj(fields)
        return (bot.strategy_id == strategy_id and bot.name == bot_name
                and bot.mode == "manual" and bot.is_live is False
                and bot.is_active is True and bot.symbol in (None, "AAPL")
                and bot.paper_initial_cash_eur == 0
                and bot.budget_total_eur == 10)
    except Exception:
        return False


async def _confirm_execute(user_id: int, proposal_id: str,
                           strategy_id: int, bot_name: str,
                           namespace: str) -> tuple[str, str]:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
    from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
    from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService
    from backend.services.finn_v2_execution_service import FinnV2ExecutionService

    _snapshot(user_id, namespace)
    async with async_session_factory() as session:
        proposal = await FinnV2ProposalRepository(session).get_by_id_for_user(
            proposal_id=proposal_id, user_id=user_id,
        )
        fields = ((proposal.payload_json or {}).get("change") or {}).get("bot_fields") if proposal else None
        if (proposal is None or proposal.operation_type != "create_bot"
                or not _safe_bot_fields(fields, strategy_id=strategy_id, bot_name=bot_name)):
            raise RuntimeError("aapl_bot_proposal_unsafe")
        payload_hash = proposal.payload_hash
        token, _ = await FinnV2ConfirmationService(session).issue_confirmation_token(
            proposal_id=proposal_id, user_id=user_id,
        )
        confirmed = await FinnV2ConfirmationService(session).confirm(
            user_id=user_id,
            request=FinnV2ConfirmationRequest(
                proposal_id=proposal_id, confirmation_token=token,
                expected_payload_hash=payload_hash,
            ),
        )
        if not confirmed.confirmed:
            raise RuntimeError("aapl_bot_confirmation_failed")
    _snapshot(user_id, namespace)
    key = f"qa-aapl-bot-execute-{uuid.uuid4().hex}"
    async with async_session_factory() as session:
        executed = await FinnV2ExecutionService(session).execute(
            proposal_id=proposal_id, user_id=user_id,
            idempotency_key=key, expected_payload_hash=payload_hash,
        )
    _snapshot(user_id, namespace)
    async with async_session_factory() as session:
        replay = await FinnV2ExecutionService(session).execute(
            proposal_id=proposal_id, user_id=user_id,
            idempotency_key=key, expected_payload_hash=payload_hash,
        )
    return executed.status, replay.status


def _verify(user_id: int, strategy_id: int, bot_name: str, namespace: str) -> None:
    counts = _snapshot(user_id, namespace)
    if (counts["bot_configs"] != 1 or counts["bot_portfolios"] != 0
            or counts["exchange_keys"] != 0
            or any(counts[table] for table in TRADE_TABLES)):
        raise RuntimeError("aapl_bot_postcondition_failed")
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """SELECT strategy_id,name,symbol,mode,is_live,is_active,
                          paper_initial_cash_eur,budget_total_eur
                   FROM bot_configs WHERE user_id=%s""", (user_id,),
            )
            row = cursor.fetchone()
            if (not row or row[0] != strategy_id or row[1] != bot_name
                    or row[2] != "AAPL" or row[3] != "manual"
                    or row[4] is not False or row[5] is not True
                    or float(row[6] or 0) != 0 or float(row[7]) != 10):
                raise RuntimeError("aapl_bot_postcondition_failed")
    finally:
        connection.close()


def _cleanup(namespace: str, user_id: int, *, strategy_id: int) -> None:
    setup_name, strategy_name, bot_name = _names(namespace)
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("aapl_bot_cleanup_failed")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            if cursor.fetchone()[0]:
                raise RuntimeError("aapl_bot_cleanup_failed")
            for table in (*TRADE_TABLES, "bot_portfolios"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("aapl_bot_cleanup_failed")
            cursor.execute("SELECT id,strategy_id,name,symbol,mode,is_live,paper_initial_cash_eur "
                           "FROM bot_configs WHERE user_id=%s FOR UPDATE", (user_id,))
            bots = cursor.fetchall()
            if (len(bots) > 1 or any(
                    bot[1] != strategy_id or bot[2] != bot_name or bot[3] != "AAPL"
                    or bot[4] != "manual" or bot[5] is not False
                    or float(bot[6] or 0) != 0 for bot in bots)):
                raise RuntimeError("aapl_bot_cleanup_failed")
            cursor.execute("SELECT name,symbol FROM setups WHERE user_id=%s", (user_id,))
            if cursor.fetchall() != [(setup_name, "AAPL")]:
                raise RuntimeError("aapl_bot_cleanup_failed")
            cursor.execute("SELECT id,name,symbol FROM strategies WHERE user_id=%s", (user_id,))
            if cursor.fetchall() != [(strategy_id, strategy_name, "AAPL")]:
                raise RuntimeError("aapl_bot_cleanup_failed")
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s", (user_id,))
            for table in DELETE_TABLES:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("aapl_bot_cleanup_failed")
        connection.commit()
    except Exception:
        connection.rollback()
        # Never touch a numeric user id without rechecking its protected
        # marker. An unsafe child is retained for exact-run audit.
        _quarantine(connection, namespace, user_id)
        raise RuntimeError("aapl_bot_cleanup_failed") from None
    finally:
        connection.close()


def _quarantine(connection, namespace: str, user_id: int) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] is not False
                    or (owner[1] or {}).get("qa_fixture") != MARKER
                    or (owner[1] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("aapl_bot_owner_unsafe")
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s", (user_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise RuntimeError("aapl_bot_cleanup_failed") from None


async def _case(namespace: str, owner: int, trace: dict) -> dict:
    user_id = strategy_id = None
    try:
        trace["stage"] = "seed"
        user_id, strategy_id = _seed(namespace, owner)
        baseline = _snapshot(user_id, namespace)
        if baseline["bot_configs"] or baseline["exchange_keys"] or any(
                baseline[table] for table in TRADE_TABLES):
            raise RuntimeError("aapl_bot_seed_unsafe")
        _, strategy_name, bot_name = _names(namespace)
        trace["stage"] = "proposal"
        proposal = await _proposal(user_id, strategy_name, bot_name)
        trace["proposal_diagnostic"] = proposal["diagnostic"]
        if (proposal["status"] != "completed" or not proposal["proposal_id"]
                or not proposal["confirmation_required"]):
            raise RuntimeError("aapl_bot_proposal_missing")
        if _snapshot(user_id, namespace) != baseline:
            raise RuntimeError("aapl_bot_postcondition_failed")
        trace["stage"] = "confirmation"
        first, replay = await _confirm_execute(
            user_id, proposal["proposal_id"], strategy_id, bot_name, namespace,
        )
        trace["first_status"], trace["replay_status"] = first, replay
        if first != "succeeded" or replay != "already_executed":
            raise RuntimeError("aapl_bot_replay_failed")
        trace["stage"] = "postcondition"
        _verify(user_id, strategy_id, bot_name, namespace)
        return {"result": "PASS", "proposal_confirmed": True,
                "single_manual_paper_bot": True, "owner_inactive": True,
                "replay": True, "no_orders_or_cash": True}
    finally:
        if user_id is not None and strategy_id is not None:
            trace["stage_before_cleanup"] = trace["stage"]
            trace["stage"] = "cleanup"
            try:
                _cleanup(namespace, user_id, strategy_id=strategy_id)
                trace["fixture_state"] = "cleaned"
            except Exception:
                trace["fixture_state"] = "quarantined"
                raise


def run(namespace: str) -> dict:
    owner = _bound_owner(namespace)
    from backend.infrastructure.database import engine
    from backend.scripts.probe_protected_paper_exit_reconciliation import _guard_live_exchange

    trace = {"stage": "seed", "fixture_state": "not_created"}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with _guard_live_exchange() as live_attempts:
            try:
                result = loop.run_until_complete(_case(namespace, owner, trace))
            except Exception as error:
                code = str(error)
                result = {"result": "FAIL",
                          "reason": code if code in FAILURES else "aapl_bot_runtime_failed",
                          "failure_stage": trace.get("stage_before_cleanup", trace["stage"])}
            result["fixture_state"] = trace["fixture_state"]
            result["first_status"] = trace.get("first_status", "not_called")
            result["replay_status"] = trace.get("replay_status", "not_called")
            if "proposal_diagnostic" in trace:
                result["proposal_diagnostic"] = trace["proposal_diagnostic"]
            result["live_calls"] = len(live_attempts)
            if live_attempts:
                result["result"] = "FAIL"
                result["reason"] = "aapl_bot_postcondition_failed"
            return result
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
        asyncio.set_event_loop(None)
