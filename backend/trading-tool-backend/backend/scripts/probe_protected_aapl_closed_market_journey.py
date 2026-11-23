"""One owner-bound AAPL planning journey; never starts a bot or places an order."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid
from decimal import Decimal

from backend.scripts import probe_protected_aapl_bot_crud as bot
from backend.scripts import probe_protected_aapl_quote_coach as quote
from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts import probe_protected_setup_strategy_journey as journey


FAILURES = frozenset({
    "aapl_journey_not_authorized", "aapl_journey_fixture_unsafe",
    "aapl_journey_quote_missing", "aapl_journey_setup_proposal_missing",
    "aapl_journey_setup_confirmation_failed", "aapl_journey_strategy_guided_failed",
    "aapl_journey_strategy_proposal_missing", "aapl_journey_strategy_confirmation_failed",
    "aapl_journey_bot_guided_failed", "aapl_journey_bot_proposal_missing",
    "aapl_journey_bot_confirmation_failed", "aapl_journey_postcondition_failed",
    "aapl_journey_cleanup_failed", "aapl_journey_runtime_failed",
})


def _bound_owner(namespace: str) -> int:
    if (not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
            or os.getenv("FINN_QA_ALLOW_AAPL_CLOSED_JOURNEY") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"):
        raise RuntimeError("aapl_journey_not_authorized")
    value = os.getenv("FINN_QA_USER_ID", "")
    if not value.isdecimal() or int(value) <= 0:
        raise RuntimeError("aapl_journey_not_authorized")
    return int(value)


def _seed(namespace: str, owner: int) -> int:
    from backend.utils.auth_utils import hash_password

    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (owner,))
            row = cursor.fetchone()
            if (not row or row[0] != "user" or row[1] is not True
                    or (row[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER):
                raise RuntimeError("aapl_journey_fixture_unsafe")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (owner,))
            if cursor.fetchone()[0]:
                raise RuntimeError("aapl_journey_fixture_unsafe")
            cursor.execute(
                """INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                   VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (f"aapl-journey-{namespace}@tradamind.example",
                 hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": bot.MARKER, "qa_namespace": namespace})),
            )
            user_id = int(cursor.fetchone()[0])
        connection.commit()
        return user_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _objects(user_id: int, namespace: str) -> dict:
    counts = bot._snapshot(user_id, namespace)
    if (counts["bot_configs"] > 1 or counts["bot_portfolios"]
            or counts["exchange_keys"]
            or any(counts[table] for table in bot.TRADE_TABLES)):
        raise RuntimeError("aapl_journey_fixture_unsafe")
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id,name,symbol FROM setups WHERE user_id=%s", (user_id,))
            setups = cursor.fetchall()
            cursor.execute("SELECT id,setup_id,name,symbol FROM strategies WHERE user_id=%s", (user_id,))
            strategies = cursor.fetchall()
            cursor.execute("SELECT id,strategy_id,name,symbol FROM bot_configs WHERE user_id=%s", (user_id,))
            bots = cursor.fetchall()
            setup_name, strategy_name, bot_name = bot._names(namespace)
            if (len(setups) > 1 or len(strategies) > 1 or len(bots) > 1
                    or any(row[1:] != (setup_name, "AAPL") for row in setups)
                    or any(row[2:] != (strategy_name, "AAPL") for row in strategies)
                    or any(row[2:] != (bot_name, "AAPL") for row in bots)
                    or (strategies and (not setups or strategies[0][1] != setups[0][0]))
                    or (bots and (not strategies or bots[0][1] != strategies[0][0]))):
                raise RuntimeError("aapl_journey_fixture_unsafe")
            return {"setup_id": setups[0][0] if setups else None,
                    "strategy_id": strategies[0][0] if strategies else None,
                    "bot_id": bots[0][0] if bots else None}
    finally:
        connection.close()


def _cleanup(namespace: str, user_id: int) -> None:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != bot.MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("aapl_journey_cleanup_failed")
            for table in (*bot.TRADE_TABLES, "bot_portfolios", "exchange_keys"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("aapl_journey_cleanup_failed")
            setup_name, strategy_name, bot_name = bot._names(namespace)
            cursor.execute("SELECT id,name,symbol FROM setups WHERE user_id=%s FOR UPDATE", (user_id,))
            setups = cursor.fetchall()
            cursor.execute("SELECT id,setup_id,name,symbol FROM strategies WHERE user_id=%s FOR UPDATE", (user_id,))
            strategies = cursor.fetchall()
            cursor.execute("""SELECT id,strategy_id,name,symbol,mode,is_live,
                                     paper_initial_cash_eur,budget_total_eur
                              FROM bot_configs WHERE user_id=%s FOR UPDATE""", (user_id,))
            bots = cursor.fetchall()
            if (len(setups) > 1 or len(strategies) > 1 or len(bots) > 1
                    or any(row[1:] != (setup_name, "AAPL") for row in setups)
                    or any(row[2:] != (strategy_name, "AAPL") for row in strategies)
                    or any(row[2:6] != (bot_name, "AAPL", "manual", False)
                           or float(row[6] or 0) != 0 or float(row[7]) != 10 for row in bots)
                    or (strategies and (not setups or strategies[0][1] != setups[0][0]))
                    or (bots and (not strategies or bots[0][1] != strategies[0][0]))):
                raise RuntimeError("aapl_journey_cleanup_failed")
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s", (user_id,))
            for table in bot.DELETE_TABLES:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("aapl_journey_cleanup_failed")
        connection.commit()
    except Exception:
        connection.rollback()
        bot._quarantine(connection, namespace, user_id)
        raise RuntimeError("aapl_journey_cleanup_failed") from None
    finally:
        connection.close()


async def _turn(user_id: int, message: str, *, conversation_id: str | None = None) -> dict:
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
                message=message, conversation_id=conversation_id, transport="chat",
                workspace_hints={"symbol": "AAPL", "quote_currency": "USD"},
                client_context={"surface": "qa_aapl_closed_market_journey"},
            ),
            request_path="/api/assistant/chat",
            request_id=f"qa-aapl-journey-{uuid.uuid4().hex}",
        )
        run_id = run.id
        await session.commit()
    await asyncio.wait_for(
        _process_finn_v2_run(run_id=run_id, owner=f"qa-aapl-journey:{uuid.uuid4().hex}"),
        timeout=90,
    )
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        saved = await gateway.get_run(run_id=run_id, user_id=user_id)
        envelope = await gateway.run_service.envelope_from_run(saved)
        row = await session.execute(text("""SELECT terminal_projection_json FROM finn_v2_runtime_contracts
                                          WHERE run_id=:run_id AND user_id=:user_id"""),
                                    {"run_id": run_id, "user_id": user_id})
        projection = dict(row.scalar_one_or_none() or {})
        response = envelope.response
        return {"status": envelope.status, "conversation_id": saved.conversation_id,
                "proposal_id": response.proposal_id if response else None,
                "confirmation_required": bool(response and response.confirmation_required),
                "answer": response.content if response else "",
                "operation": projection.get("final_operation_id") or projection.get("initial_operation_id"),
                "guided_operation": (projection.get("action_draft") or {}).get("operation_id"),
                "supplied_inputs": dict(projection.get("supplied_inputs") or {}),
                "dispatch_count": projection.get("dispatch_count"),
                "attempt_count": projection.get("attempt_count")}


async def _case(namespace: str, owner: int, trace: dict) -> dict:
    user_id = None
    try:
        trace["stage"] = "seed"
        user_id = _seed(namespace, owner)
        baseline = bot._snapshot(user_id, namespace)
        if _objects(user_id, namespace) != {"setup_id": None, "strategy_id": None, "bot_id": None}:
            raise RuntimeError("aapl_journey_fixture_unsafe")
        if any(baseline.values()):
            raise RuntimeError("aapl_journey_fixture_unsafe")

        trace["stage"] = "quote"
        source = quote._source()
        quote_turn = await _turn(user_id,
            "Wat is de laatst beschikbare AAPL-koers in USD met bronmoment? "
            "Gebruik die alleen voor planning; dit is geen actuele uitvoeringskoers. Plaats geen order.")
        if (quote_turn["status"] != "completed" or quote_turn["proposal_id"]
                or not quote._answer_current_price(quote_turn["answer"], source["price"])
                or not quote._answer_moments(quote_turn["answer"], source["at"], source["price"])["current_source_time_explained"]):
            raise RuntimeError("aapl_journey_quote_missing")

        setup_name, strategy_name, bot_name = bot._names(namespace)
        conversation = quote_turn["conversation_id"]
        trace["stage"] = "setup_proposal"
        setup = await _turn(user_id,
            f"Ik wil los een swing-setup voor AAPL op 1 dag, genaamd {setup_name}. "
            "Bereid alleen de setup voor en toon eerst het voorstel; plaats geen order.",
            conversation_id=conversation)
        if (setup["conversation_id"] != conversation or setup["status"] != "completed"
                or not setup["proposal_id"] or not setup["confirmation_required"]
                or setup["operation"] != "create_setup"):
            raise RuntimeError("aapl_journey_setup_proposal_missing")
        if _objects(user_id, namespace)["setup_id"] is not None:
            raise RuntimeError("aapl_journey_postcondition_failed")
        trace["stage"] = "setup_confirmation"
        setup_result = await journey._confirm_and_execute(user_id, setup["proposal_id"], trace)
        ids = _objects(user_id, namespace)
        if (setup_result["conversation_id"] != conversation or not ids["setup_id"]
                or ids["strategy_id"] or ids["bot_id"]
                or (setup_result["next_step"] or {}).get("setup_id") != ids["setup_id"]):
            raise RuntimeError("aapl_journey_setup_confirmation_failed")

        trace["stage"] = "strategy_guided"
        yes = await _turn(user_id, "ja", conversation_id=conversation)
        if (yes["conversation_id"] != conversation
                or "create_strategy" not in {yes["operation"], yes["guided_operation"]}
                or str(yes["supplied_inputs"].get("setup_id")) != str(ids["setup_id"])):
            raise RuntimeError("aapl_journey_strategy_guided_failed")
        trace["stage"] = "strategy_proposal"
        entry = int(source["price"].quantize(Decimal("1")))
        stop = max(1, entry - 10)
        target = entry + 20
        strategy = await _turn(user_id,
            f"Noem die strategie {strategy_name}. Vaste uitvoering van 10 euro, "
            f"entry {entry} USD, stop-loss {stop} USD, target {target} USD, "
            "gebalanceerd risico. "
            "Gebruik de laatst gedateerde koers alleen voor planning. Toon eerst een voorstel, maak geen bot.",
            conversation_id=conversation)
        if (strategy["conversation_id"] != conversation or strategy["status"] != "completed"
                or not strategy["proposal_id"] or not strategy["confirmation_required"]
                or strategy["operation"] != "create_strategy"
                or str(strategy["supplied_inputs"].get("setup_id")) != str(ids["setup_id"])):
            raise RuntimeError("aapl_journey_strategy_proposal_missing")
        if _objects(user_id, namespace)["strategy_id"] is not None:
            raise RuntimeError("aapl_journey_postcondition_failed")
        trace["stage"] = "strategy_confirmation"
        strategy_result = await journey._confirm_and_execute(user_id, strategy["proposal_id"], trace)
        ids = _objects(user_id, namespace)
        if (strategy_result["conversation_id"] != conversation or not ids["strategy_id"]
                or ids["bot_id"]
                or (strategy_result["next_step"] or {}).get("strategy_id") != ids["strategy_id"]):
            raise RuntimeError("aapl_journey_strategy_confirmation_failed")

        trace["stage"] = "bot_guided"
        bot_yes = await _turn(user_id, "ja", conversation_id=conversation)
        if (bot_yes["conversation_id"] != conversation
                or "create_bot" not in {bot_yes["operation"], bot_yes["guided_operation"]}
                or str(bot_yes["supplied_inputs"].get("strategy_id")) != str(ids["strategy_id"])):
            raise RuntimeError("aapl_journey_bot_guided_failed")
        trace["stage"] = "bot_proposal"
        proposed_bot = await _turn(user_id,
            f"Maak een handmatige Paper-botconfiguratie met naam {bot_name} "
            f"voor mijn bestaande AAPL-strategie {strategy_name}. Totaalbudget 10 euro "
            "en Paper-startkapitaal 0 euro. Toon eerst een voorstel; plaats geen order "
            "en activeer geen live trading.", conversation_id=conversation)
        if (proposed_bot["conversation_id"] != conversation
                or proposed_bot["status"] != "completed" or not proposed_bot["proposal_id"]
                or not proposed_bot["confirmation_required"]
                or proposed_bot["operation"] != "create_bot"):
            raise RuntimeError("aapl_journey_bot_proposal_missing")
        if _objects(user_id, namespace)["bot_id"] is not None:
            raise RuntimeError("aapl_journey_postcondition_failed")
        trace["stage"] = "bot_confirmation"
        trace["bot_confirmation_started"] = True
        first, replay = await bot._confirm_execute(
            user_id, proposed_bot["proposal_id"], ids["strategy_id"], bot_name, namespace)
        trace["bot_confirmed"] = True
        trace["bot_execution_succeeded"] = first == "succeeded"
        if first != "succeeded" or replay != "already_executed":
            raise RuntimeError("aapl_journey_bot_confirmation_failed")
        trace["stage"] = "postcondition"
        bot._verify(user_id, ids["strategy_id"], bot_name, namespace)
        if _objects(user_id, namespace)["bot_id"] is None:
            raise RuntimeError("aapl_journey_postcondition_failed")
        if (trace.get("confirmed_count") != 2 or trace.get("executed_count") != 2
                or any(bot._snapshot(user_id, namespace)[table] for table in (*bot.TRADE_TABLES, "exchange_keys"))):
            raise RuntimeError("aapl_journey_postcondition_failed")
        return {"result": "PASS", "quote_dated_for_planning": True,
                "one_conversation": True, "setup_strategy_bot_lineage": True,
                "three_separate_confirmations": True, "replay": True,
                "no_worker_or_order": True, "owner_inactive": True}
    finally:
        if user_id is not None:
            trace["stage_before_cleanup"] = trace["stage"]
            trace["stage"] = "cleanup"
            try:
                _cleanup(namespace, user_id)
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
                result = {"result": "FAIL", "reason": code if code in FAILURES
                          else "aapl_journey_runtime_failed",
                          "failure_stage": trace.get("stage_before_cleanup", trace["stage"])}
            if "execution_diagnostic" in trace:
                result["execution_diagnostic"] = trace["execution_diagnostic"].copy()
            result["fixture_state"] = trace["fixture_state"]
            bot_known = trace.get("bot_execution_succeeded")
            result["confirmations"] = (None if trace.get("bot_confirmation_started") and not trace.get("bot_confirmed")
                                       else trace.get("confirmed_count", 0) + int(bool(trace.get("bot_confirmed"))))
            result["nonfinancial_executions"] = (None if trace.get("bot_confirmation_started") and bot_known is None
                                                  else trace.get("executed_count", 0) + int(bool(bot_known)))
            result["live_calls"] = len(live_attempts)
            if live_attempts:
                result["result"] = "FAIL"
                result["reason"] = "aapl_journey_postcondition_failed"
            return result
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
        asyncio.set_event_loop(None)
