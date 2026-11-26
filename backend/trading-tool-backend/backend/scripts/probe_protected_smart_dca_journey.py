"""Protected FINN Smart DCA setup and manual Paper bot journey.

The owner remains inactive. This probe confirms configuration only; it never
funds a bot, invokes a worker, or places an order.
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid

from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts import probe_protected_aapl_bot_crud as bot_reference

MARKER = "finn_smart_dca_journey_qa_v1"
FLAG = "FINN_QA_ALLOW_SMART_DCA_JOURNEY"
EXECUTION_STATUSES = frozenset({"started", "blocked", "succeeded", "failed", "already_executed"})
EXECUTION_CODES = frozenset({
    "proposal_not_confirmed", "proposal_expired", "proposal_payload_hash_mismatch",
    "proposal_evidence_hash_mismatch", "step_up_required", "kill_switch_enabled",
    "feature_disabled", "bot_action_disabled", "live_action_disabled",
    "shadow_mode_execution_blocked",
})
EXCEPTION_CLASSES = frozenset({
    "AttributeError", "DataError", "IntegrityError", "KeyError", "LookupError",
    "OperationalError", "ProgrammingError", "RuntimeError", "TimeoutError",
    "TypeError", "ValueError",
})
FAILURES = frozenset({
    "smart_dca_journey_not_authorized", "smart_dca_journey_fixture_unsafe",
    "smart_dca_journey_setup_proposal_missing", "smart_dca_journey_setup_proposal_unsafe",
    "smart_dca_journey_setup_confirmation_failed", "smart_dca_journey_bot_proposal_missing",
    "smart_dca_journey_bot_proposal_unsafe", "smart_dca_journey_bot_confirmation_failed",
    "smart_dca_journey_postcondition_failed", "smart_dca_journey_cleanup_failed",
    "smart_dca_journey_quarantine_unverified",
    "smart_dca_journey_runtime_failed",
})
TRADE_TABLES = bot_reference.TRADE_TABLES
DELETE_TABLES = bot_reference.DELETE_TABLES


def _names(namespace: str) -> tuple[str, str]:
    return f"QA BTC Smart DCA {namespace}", f"QA BTC Smart Bot {namespace}"


def _expected_setup_fields(name: str) -> dict:
    return {
        "name": name, "symbol": "BTC", "quote_currency": "USDT",
        "timeframe": "1D", "setup_type": "dca", "dca_trigger_mode": "benchmark",
        "dca_frequency": "weekly", "dca_amount_mode": "score_bands",
        "score_source": "benchmark_score", "low_threshold": 26, "high_threshold": 76,
        "low_score_percent": 150, "mid_score_percent": 100,
        "high_score_percent": 50, "base_amount": 200, "dca_day": None,
    }


def _expected_curve(name: str) -> dict:
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan

    return split_confirmed_dca_plan(_expected_setup_fields(name))[1]["decision_curve"]


def _expected_amount_bounds(name: str) -> tuple[float, float]:
    from backend.domain.finn_dca_plan_contract import (
        confirmed_dca_amount_bounds, split_confirmed_dca_plan,
    )

    _, strategy = split_confirmed_dca_plan(_expected_setup_fields(name))
    bounds = confirmed_dca_amount_bounds({"setup_type": "dca", **strategy})
    if bounds is None:
        raise RuntimeError("smart_dca_journey_fixture_unsafe")
    return bounds


def _safe_status(value: object) -> str:
    return value if isinstance(value, str) and value in EXECUTION_STATUSES else "other"


def _safe_codes(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    safe = set()
    for value_item in value[:8]:
        if isinstance(value_item, str) and value_item in EXECUTION_CODES:
            safe.add(value_item)
        elif isinstance(value_item, str) and "totale botlimiet" in value_item.lower():
            safe.add("bot_budget_below_plan")
        elif isinstance(value_item, str) and "daglimiet en maximale order" in value_item.lower():
            safe.add("bot_order_limits_below_plan")
        elif isinstance(value_item, str) and "paper-bot heeft minstens" in value_item.lower():
            safe.add("paper_cash_below_plan")
        else:
            safe.add("other")
    return sorted(safe)


def _bound_owner(namespace: str) -> int:
    raw = os.getenv("FINN_QA_USER_ID", "")
    if (not fixture.NAMESPACE_PATTERN.fullmatch(namespace)
            or os.getenv(FLAG) != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"
            or not raw.isdecimal() or int(raw) <= 0):
        raise RuntimeError("smart_dca_journey_not_authorized")
    return int(raw)


def _seed(namespace: str, owner: int) -> int:
    from backend.utils.auth_utils import hash_password

    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (owner,))
            row = cursor.fetchone()
            if (not row or row[0] != "user" or row[1] is not True
                    or (row[2] or {}).get("qa_fixture") != fixture.QA_OWNER_MARKER):
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
            cursor.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (owner,))
            if cursor.fetchone()[0]:
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
            cursor.execute(
                """INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                   VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (f"smart-dca-journey-{namespace}@tradamind.example",
                 hash_password(secrets.token_urlsafe(48)),
                 json.dumps({"qa_fixture": MARKER, "qa_namespace": namespace})),
            )
            user_id = int(cursor.fetchone()[0])
        connection.commit()
        return user_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _snapshot(user_id: int, namespace: str) -> dict[str, int]:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
            counts = {}
            for table in (*TRADE_TABLES, "bot_portfolios", "bot_configs",
                          "setups", "strategies", "exchange_keys"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                counts[table] = int(cursor.fetchone()[0])
            return counts
    finally:
        connection.close()


def _saved(user_id: int, namespace: str, *, connection=None, locked: bool = False) -> dict:
    if locked != (connection is not None):
        raise RuntimeError("smart_dca_journey_fixture_unsafe")
    if connection is None:
        counts = _snapshot(user_id, namespace)
        if (any(counts[table] for table in (*TRADE_TABLES, "bot_portfolios", "exchange_keys"))
                or counts["setups"] > 1 or counts["strategies"] > 1 or counts["bot_configs"] > 1):
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
    setup_name, bot_name = _names(namespace)
    own_connection = connection is None
    if own_connection:
        connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            if locked:
                for table in (*TRADE_TABLES, "bot_portfolios", "exchange_keys"):
                    cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                    if cursor.fetchone()[0]:
                        raise RuntimeError("smart_dca_journey_fixture_unsafe")
            suffix = " FOR UPDATE OF s" if locked else ""
            cursor.execute(f"""SELECT s.id,s.name,s.symbol,s.timeframe,s.setup_type,
                                     s.dca_trigger_mode,s.dca_frequency,s.dca_day,
                                     s.min_benchmark_score,s.max_benchmark_score,
                                     s.market_id,m.asset_symbol,m.quote_currency
                              FROM setups s LEFT JOIN trading_markets m ON m.id=s.market_id
                              WHERE s.user_id=%s{suffix}""", (user_id,))
            setups = cursor.fetchall()
            suffix = " FOR UPDATE" if locked else ""
            cursor.execute(f"""SELECT id,setup_id,name,symbol,execution_mode,base_amount,
                                     decision_curve,market_id,data
                              FROM strategies WHERE user_id=%s{suffix}""", (user_id,))
            strategies = cursor.fetchall()
            cursor.execute(f"""SELECT id,strategy_id,name,symbol,mode,is_live,is_active,
                                     paper_initial_cash_eur,budget_total_eur,market_id,
                                     budget_daily_limit_eur,budget_min_order_eur,budget_max_order_eur
                              FROM bot_configs WHERE user_id=%s{suffix}""", (user_id,))
            bots = cursor.fetchall()
        if (setups and (len(setups) != 1
                        or setups[0][1:8] !=
                        (setup_name, "BTC", "1D", "dca", "benchmark", "weekly", None)
                        or setups[0][8] is None or float(setups[0][8]) != 0
                        or setups[0][9] is None or float(setups[0][9]) != 100
                        or not setups[0][10]
                        or setups[0][11:] != ("BTC", "USDT"))):
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
        if strategies:
            if not setups or len(strategies) != 1:
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
            strategy = strategies[0]
            curve = strategy[6]
            if isinstance(curve, str):
                curve = json.loads(curve)
            data = strategy[8]
            if isinstance(data, str):
                data = json.loads(data)
            if (strategy[1] != setups[0][0]
                    or strategy[2] != f"{setup_name} Strategy"
                    or strategy[3] != "BTC"
                    or strategy[4] != "custom"
                    or float(strategy[5] or 0) != 200
                    or curve != _expected_curve(setup_name)
                    or strategy[7] != setups[0][10]
                    or not isinstance(data, dict)
                    or data.get("dca_amount_semantics") != "planned_exact"):
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
        if bots:
            if not strategies or len(bots) != 1:
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
            row = bots[0]
            if (row[1] != strategies[0][0] or row[2:6] !=
                    (bot_name, "BTC", "manual", False)
                    or row[6] is not True
                    or not _safe_bot_limits(row[7], row[8], row[10], row[11], row[12], setup_name)
                    or row[9] != setups[0][10]):
                raise RuntimeError("smart_dca_journey_fixture_unsafe")
        return {"setup_id": setups[0][0] if setups else None,
                "strategy_id": strategies[0][0] if strategies else None,
                "bot_id": bots[0][0] if bots else None}
    finally:
        if own_connection:
            connection.close()


def _quarantine(connection, namespace: str, user_id: int) -> None:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("smart_dca_journey_cleanup_failed")
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s", (user_id,))
        connection.commit()
    except Exception:
        connection.rollback()
        raise RuntimeError("smart_dca_journey_cleanup_failed") from None


def _cleanup(namespace: str, user_id: int) -> None:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT role,is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            owner = cursor.fetchone()
            if (not owner or owner[0] != "user" or owner[1] is not False
                    or (owner[2] or {}).get("qa_fixture") != MARKER
                    or (owner[2] or {}).get("qa_namespace") != namespace):
                raise RuntimeError("smart_dca_journey_cleanup_failed")
            # Lock and validate every owned setup, strategy and bot inside this
            # transaction before any deletion. Unknown rows stay quarantined.
            _saved(user_id, namespace, connection=connection, locked=True)
            for table in (*TRADE_TABLES, "bot_portfolios", "exchange_keys"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                if cursor.fetchone()[0]:
                    raise RuntimeError("smart_dca_journey_cleanup_failed")
            cursor.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s", (user_id,))
            for table in DELETE_TABLES:
                cursor.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cursor.fetchone()[0] is not None:
                    cursor.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
            if cursor.rowcount != 1:
                raise RuntimeError("smart_dca_journey_cleanup_failed")
        connection.commit()
    except Exception:
        connection.rollback()
        try:
            _quarantine(connection, namespace, user_id)
        except Exception:
            raise RuntimeError("smart_dca_journey_quarantine_unverified") from None
        raise RuntimeError("smart_dca_journey_cleanup_failed") from None
    finally:
        connection.close()


def _safe_setup(fields: object, name: str) -> bool:
    if not isinstance(fields, dict):
        return False
    expected = _expected_setup_fields(name)
    return (all(fields.get(key) == value for key, value in expected.items())
            and fields.get("dca_month_day") is None
            and fields.get("plan_scope") != "setup_only"
            and fields.get("min_benchmark_score") in (None, 0)
            and fields.get("max_benchmark_score") in (None, 100))


def _safe_bot(fields: object, strategy_id: int, name: str, setup_name: str) -> bool:
    if not isinstance(fields, dict):
        return False
    from backend.schemas.bot_schema import BotConfigCreateSchema
    try:
        bot = BotConfigCreateSchema.parse_obj(fields)
    except Exception:
        return False
    return (bot.strategy_id == strategy_id and bot.name == name
            and bot.symbol in (None, "BTC") and bot.mode == "manual"
            and bot.is_live is False and bot.is_active is True
            and _safe_bot_limits(
                bot.paper_initial_cash_eur, bot.budget_total_eur,
                bot.budget_daily_limit_eur, bot.budget_min_order_eur,
                bot.budget_max_order_eur, setup_name,
            ))


def _safe_bot_limits(cash: object, total: object, daily: object,
                     minimum: object, maximum: object, setup_name: str) -> bool:
    try:
        minimum_plan, maximum_plan = _expected_amount_bounds(setup_name)
        return (float(cash or 0) == 0
                and float(total or 0) == maximum_plan
                and (float(daily or 0) == 0 or float(daily) >= maximum_plan)
                and 0 <= float(minimum or 0) <= minimum_plan
                and (float(maximum or 0) == 0 or float(maximum) >= maximum_plan))
    except (TypeError, ValueError):
        return False


async def _proposal_fields(user_id: int, proposal_id: str, operation: str, key: str) -> object:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository

    async with async_session_factory() as session:
        proposal = await FinnV2ProposalRepository(session).get_by_id_for_user(
            proposal_id=proposal_id, user_id=user_id)
        if proposal is None or proposal.operation_type != operation:
            return None
        return ((proposal.payload_json or {}).get("change") or {}).get(key)


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
                workspace_hints={"symbol": "BTC", "quote_currency": "USDT"},
                client_context={"surface": "qa_smart_dca_journey"},
            ),
            request_path="/api/assistant/chat",
            request_id=f"qa-smart-dca-journey-{uuid.uuid4().hex}",
        )
        run_id = run.id
        await session.commit()
    await asyncio.wait_for(
        _process_finn_v2_run(run_id=run_id, owner=f"qa-smart-dca-journey:{uuid.uuid4().hex}"),
        timeout=90,
    )
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        saved = await gateway.get_run(run_id=run_id, user_id=user_id)
        envelope = await gateway.run_service.envelope_from_run(saved)
        row = await session.execute(text("""SELECT terminal_projection_json
            FROM finn_v2_runtime_contracts WHERE run_id=:run_id AND user_id=:user_id"""),
            {"run_id": run_id, "user_id": user_id})
        projection = dict(row.scalar_one_or_none() or {})
        response = envelope.response
        return {"status": envelope.status, "conversation_id": saved.conversation_id,
                "proposal_id": response.proposal_id if response else None,
                "confirmation_required": bool(response and response.confirmation_required),
                "operation": projection.get("final_operation_id") or projection.get("initial_operation_id")}


async def _case(namespace: str, owner: int, trace: dict) -> dict:
    user_id = None
    try:
        trace["stage"] = "seed"
        user_id = _seed(namespace, owner)
        if any(_snapshot(user_id, namespace).values()):
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
        setup_name, bot_name = _names(namespace)
        trace["stage"] = "setup_proposal"
        setup = await _turn(
            user_id,
            f"Maak een nieuwe BTC/USDT Smart DCA-setup met de naam {setup_name} op timeframe 1D. "
            "Basisbedrag €200, maximaal één aankoop per week. Gebruik de volledige gewogen "
            "benchmark van Markt, Macro en Technisch. Score onder 26: 150%; van 26 tot onder "
            "76: 100%; vanaf 76: 50%. Toon eerst de conceptkaart; geen bot en geen order.",
        )
        if (setup["status"] != "completed" or not setup["proposal_id"]
                or not setup["confirmation_required"]
                or setup["operation"] != "create_setup"):
            raise RuntimeError("smart_dca_journey_setup_proposal_missing")
        fields = await _proposal_fields(user_id, setup["proposal_id"], "create_setup", "setup_fields")
        if not _safe_setup(fields, setup_name):
            raise RuntimeError("smart_dca_journey_setup_proposal_unsafe")
        if any(_snapshot(user_id, namespace).values()):
            raise RuntimeError("smart_dca_journey_postcondition_failed")
        conversation = setup["conversation_id"]
        trace["stage"] = "setup_confirmation"
        first, replay, result_conversation = await _confirm_configuration(
            user_id, setup["proposal_id"], namespace, "create_setup",
            "setup_fields", lambda fields: _safe_setup(fields, setup_name), trace)
        saved = _saved(user_id, namespace)
        if (first != "succeeded" or replay != "already_executed"
                or result_conversation != conversation or not saved["setup_id"]
                or not saved["strategy_id"] or saved["bot_id"]):
            raise RuntimeError("smart_dca_journey_setup_confirmation_failed")
        trace["stage"] = "bot_proposal"
        proposed_bot = await _turn(
            user_id,
            f"Maak een handmatige Paper-botconfiguratie met naam {bot_name} voor mijn "
            f"bestaande BTC/USDT-strategie {setup_name} Strategy bij setup {setup_name}. "
            f"Totaalbudget {_expected_amount_bounds(setup_name)[1]:g} euro en "
            "Paper-startkapitaal 0 euro. Toon eerst een voorstel; "
            "plaats geen order en activeer geen live trading.",
            conversation_id=conversation,
        )
        if (proposed_bot["conversation_id"] != conversation
                or proposed_bot["status"] != "completed" or not proposed_bot["proposal_id"]
                or not proposed_bot["confirmation_required"]
                or proposed_bot["operation"] != "create_bot"):
            raise RuntimeError("smart_dca_journey_bot_proposal_missing")
        fields = await _proposal_fields(user_id, proposed_bot["proposal_id"], "create_bot", "bot_fields")
        if not _safe_bot(fields, saved["strategy_id"], bot_name, setup_name):
            raise RuntimeError("smart_dca_journey_bot_proposal_unsafe")
        if _saved(user_id, namespace)["bot_id"] is not None:
            raise RuntimeError("smart_dca_journey_postcondition_failed")
        trace["stage"] = "bot_confirmation"
        trace["bot_confirmation_started"] = True
        first, replay, result_conversation = await _confirm_configuration(
            user_id, proposed_bot["proposal_id"], namespace, "create_bot",
            "bot_fields",
            lambda fields: _safe_bot(fields, saved["strategy_id"], bot_name, setup_name), trace)
        trace["bot_confirmed"] = True
        trace["bot_execution_succeeded"] = first == "succeeded"
        if (first != "succeeded" or replay != "already_executed"
                or result_conversation != conversation):
            raise RuntimeError("smart_dca_journey_bot_confirmation_failed")
        if _saved(user_id, namespace)["bot_id"] is None:
            raise RuntimeError("smart_dca_journey_postcondition_failed")
        return {"result": "PASS", "one_conversation": True,
                "score_bands_verified": True, "setup_strategy_bot_lineage": True,
                "two_separate_confirmations": True, "replay": True,
                "no_worker_or_order": True, "owner_inactive": True}
    finally:
        if user_id is not None:
            trace["stage_before_cleanup"] = trace["stage"]
            trace["stage"] = "cleanup"
            try:
                _cleanup(namespace, user_id)
                trace["fixture_state"] = "cleaned"
            except Exception as error:
                trace["fixture_state"] = (
                    "quarantine_unverified"
                    if str(error) == "smart_dca_journey_quarantine_unverified"
                    else "quarantined")
                raise


async def _confirm_configuration(user_id: int, proposal_id: str, namespace: str,
                                 operation: str, field_key: str, is_safe,
                                 trace: dict) -> tuple[str, str, str | None]:
    diagnostic = {
        "stage": "proposal_lookup", "first_status": "not_called", "first_codes": [],
        "replay_status": "not_called", "replay_codes": [],
        "exception_class": None, "exception_stage": None,
    }
    if operation == "create_bot":
        trace["bot_execution_diagnostic"] = diagnostic
    try:
        return await _confirm_configuration_impl(
            user_id, proposal_id, namespace, operation, field_key, is_safe,
            trace, diagnostic,
        )
    except Exception as error:
        name = type(error).__name__
        diagnostic["exception_class"] = name if name in EXCEPTION_CLASSES else "other"
        diagnostic["exception_stage"] = diagnostic["stage"]
        raise


async def _confirm_configuration_impl(user_id: int, proposal_id: str, namespace: str,
                                      operation: str, field_key: str, is_safe,
                                      trace: dict, diagnostic: dict) -> tuple[str, str, str | None]:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
    from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
    from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService
    from backend.services.finn_v2_execution_service import FinnV2ExecutionService

    diagnostic["stage"] = "preflight"
    _snapshot(user_id, namespace)
    async with async_session_factory() as session:
        diagnostic["stage"] = "proposal_lookup"
        proposal = await FinnV2ProposalRepository(session).get_by_id_for_user(
            proposal_id=proposal_id, user_id=user_id)
        fields = ((proposal.payload_json or {}).get("change") or {}).get(field_key) if proposal else None
        if proposal is None or proposal.operation_type != operation or not is_safe(fields):
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
        payload_hash = proposal.payload_hash
        diagnostic["stage"] = "confirmation"
        token, _ = await FinnV2ConfirmationService(session).issue_confirmation_token(
            proposal_id=proposal_id, user_id=user_id)
        confirmed = await FinnV2ConfirmationService(session).confirm(
            user_id=user_id,
            request=FinnV2ConfirmationRequest(
                proposal_id=proposal_id, confirmation_token=token,
                expected_payload_hash=payload_hash))
        if not confirmed.confirmed:
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
    trace["confirmed_count"] = trace.get("confirmed_count", 0) + 1
    _snapshot(user_id, namespace)
    key = f"qa-smart-dca-bot-{uuid.uuid4().hex}"
    diagnostic["stage"] = "first_execute"
    async with async_session_factory() as session:
        proposal = await FinnV2ProposalRepository(session).get_by_id_for_user(
            proposal_id=proposal_id, user_id=user_id)
        fields = ((proposal.payload_json or {}).get("change") or {}).get(field_key) if proposal else None
        if (proposal is None or proposal.operation_type != operation
                or proposal.payload_hash != payload_hash or not is_safe(fields)):
            raise RuntimeError("smart_dca_journey_fixture_unsafe")
        first = await FinnV2ExecutionService(session).execute(
            proposal_id=proposal_id, user_id=user_id,
            idempotency_key=key, expected_payload_hash=payload_hash)
        diagnostic["first_status"] = _safe_status(first.status)
        diagnostic["first_codes"] = _safe_codes(getattr(first, "error_codes", None))
    if first.status == "succeeded":
        trace["executed_count"] = trace.get("executed_count", 0) + 1
    _snapshot(user_id, namespace)
    diagnostic["stage"] = "replay_execute"
    async with async_session_factory() as session:
        replay = await FinnV2ExecutionService(session).execute(
            proposal_id=proposal_id, user_id=user_id,
            idempotency_key=key, expected_payload_hash=payload_hash)
        diagnostic["replay_status"] = _safe_status(replay.status)
        diagnostic["replay_codes"] = _safe_codes(getattr(replay, "error_codes", None))
    diagnostic["stage"] = "replay_check"
    return first.status, replay.status, first.conversation_id


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
                          "reason": code if code in FAILURES else "smart_dca_journey_runtime_failed",
                          "failure_stage": trace.get("stage_before_cleanup", trace["stage"])}
            result["fixture_state"] = trace["fixture_state"]
            bot_known = trace.get("bot_execution_succeeded")
            result["confirmations"] = (
                None if trace.get("bot_confirmation_started") and not trace.get("bot_confirmed")
                else trace.get("confirmed_count", 0))
            result["nonfinancial_executions"] = (
                None if trace.get("bot_confirmation_started") and bot_known is None
                else trace.get("executed_count", 0))
            if "bot_execution_diagnostic" in trace:
                result["bot_execution_diagnostic"] = trace["bot_execution_diagnostic"]
            result["live_calls"] = len(live_attempts)
            if live_attempts:
                result["result"] = "FAIL"
                result["reason"] = "smart_dca_journey_postcondition_failed"
            return result
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
        asyncio.set_event_loop(None)
