"""Protected, owner-bound setup -> strategy -> Paper continuation probe.

The child is inactive and has no exchange keys. Only setup and strategy are
confirmed; a Paper bot is neither proposed for execution nor created.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

from backend.scripts import probe_protected_coach_feed as feed_probe
from backend.scripts.probe_protected_account_answer import _read_tool_results
from backend.scripts.probe_protected_coach_feed_journey import _date_in_answer, _score_in_answer
from backend.scripts import probe_protected_score2_stale_paper as fixture
from backend.scripts.probe_protected_trader_fixture_audit import JOURNEY_EXECUTION_CODES


FAILURES = frozenset({
    "journey_not_authorized", "journey_fixture_unsafe", "journey_setup_missing",
    "journey_setup_proposal_missing", "journey_setup_confirmation_failed",
    "journey_strategy_card_missing", "journey_strategy_card_stale", "journey_strategy_guided_failed",
    "journey_strategy_proposal_missing", "journey_strategy_confirmation_failed",
    "journey_paper_card_missing", "journey_paper_guided_failed",
    "journey_owner_scope_failed", "journey_replay_failed",
    "journey_feed_discuss_failed",
    "journey_strategy_card_copy_failed", "journey_strategy_source_missing",
    "journey_strategy_absence_unverified", "journey_strategy_score_source_missing",
    "journey_strategy_advice_missing",
    "journey_feed_lineage_failed",
    "journey_unexpected_bot_or_order", "journey_cleanup_failed",
    "journey_runtime_failed",
})
EXECUTION_STATUSES = frozenset({"started", "blocked", "succeeded", "failed", "already_executed"})
EXCEPTION_CLASSES = frozenset({
    "AttributeError", "DataError", "IntegrityError", "KeyError", "LookupError",
    "OperationalError", "ProgrammingError", "RuntimeError", "TimeoutError",
    "TypeError", "ValueError",
})


def _safe_status(value: object) -> str:
    return value if isinstance(value, str) and value in EXECUTION_STATUSES else "other"


def _safe_codes(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return sorted({
        code if isinstance(code, str) and code in JOURNEY_EXECUTION_CODES else "other"
        for code in value[:8]
    })


def _bound_owner(namespace: str) -> int:
    if (os.getenv("FINN_QA_ALLOW_SETUP_STRATEGY_JOURNEY") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"
            or not fixture.NAMESPACE_PATTERN.fullmatch(namespace)):
        raise RuntimeError("journey_not_authorized")
    value = os.getenv("FINN_QA_USER_ID", "")
    if not value.isdecimal() or int(value) <= 0:
        raise RuntimeError("journey_not_authorized")
    return int(value)


def _snapshot(user_id: int) -> dict:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            counts = {}
            for table in ("setups", "strategies", "bot_configs", "bot_orders",
                          "bot_executions", "exchange_keys"):
                cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=%s", (user_id,))
                counts[table] = int(cursor.fetchone()[0])
            cursor.execute("""SELECT COUNT(*) FROM bot_configs
                              WHERE user_id=%s AND (is_live=TRUE OR is_active=TRUE)""", (user_id,))
            counts["active_or_live_bots"] = int(cursor.fetchone()[0])
            cursor.execute("""SELECT COUNT(*) FROM watchlists
                              WHERE user_id=%s AND symbol='BTC'""", (user_id,))
            counts["btc_watchlist"] = int(cursor.fetchone()[0])
            return counts
    finally:
        connection.close()


async def _turn(user_id: int, message: str, *, conversation_id: str | None = None,
                feed_item_id: str | None = None) -> dict:
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
                client_context={"surface": "qa_setup_strategy_journey",
                                **({"feed_item_id": feed_item_id} if feed_item_id else {})},
            ),
            request_path="/api/assistant/chat",
            request_id=f"qa-journey-{uuid.uuid4().hex}",
        )
        run_id = run.id
        await session.commit()
    await asyncio.wait_for(
        _process_finn_v2_run(run_id=run_id, owner=f"qa-journey:{uuid.uuid4().hex}"),
        timeout=90,
    )
    async with async_session_factory() as session:
        gateway = FinnV2GatewayService(session)
        saved = await gateway.get_run(run_id=run_id, user_id=user_id)
        envelope = await gateway.run_service.envelope_from_run(saved)
        response = envelope.response
        projection_row = await session.execute(text("""SELECT terminal_projection_json
            FROM finn_v2_runtime_contracts WHERE run_id=:run_id"""), {"run_id": run_id})
        projection = dict(projection_row.scalar_one_or_none() or {})
        return {
            "status": envelope.status,
            "run_id": run_id,
            "conversation_id": saved.conversation_id,
            "content": response.content if response else None,
            "proposal_id": response.proposal_id if response else None,
            "confirmation_required": bool(response and response.confirmation_required),
            "error_code": envelope.error_code,
            "operation_id": projection.get("final_operation_id") or projection.get("initial_operation_id"),
            "guided_operation": (projection.get("action_draft") or {}).get("operation_id"),
            "supplied_inputs": dict(projection.get("supplied_inputs") or {}),
            "dispatch_count": projection.get("dispatch_count"),
            "attempt_count": projection.get("attempt_count"),
        }


async def _confirm_and_execute(user_id: int, proposal_id: str, trace: dict) -> dict:
    diagnostic = {
        "operation": "unknown", "stage": "proposal_lookup",
        "first_status": "not_called", "first_codes": [],
        "replay_status": "not_called", "replay_codes": [],
        "next_step_match": None, "exception_class": None, "exception_stage": None,
    }
    trace["execution_diagnostic"] = diagnostic
    try:
        return await _confirm_and_execute_impl(user_id, proposal_id, trace, diagnostic)
    except Exception as error:
        name = type(error).__name__
        diagnostic["exception_class"] = name if name in EXCEPTION_CLASSES else "other"
        diagnostic["exception_stage"] = diagnostic["stage"]
        raise


async def _confirm_and_execute_impl(user_id: int, proposal_id: str, trace: dict,
                                    diagnostic: dict) -> dict:
    from backend.infrastructure.database import async_session_factory
    from backend.infrastructure.repositories.finn_v2_proposal_repository import FinnV2ProposalRepository
    from backend.schemas.finn_v2_confirmation_schema import FinnV2ConfirmationRequest
    from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService
    from backend.services.finn_v2_execution_service import FinnV2ExecutionService

    async with async_session_factory() as session:
        proposal = await FinnV2ProposalRepository(session).get_by_id_for_user(
            proposal_id=proposal_id, user_id=user_id,
        )
        if proposal is None or proposal.operation_type not in {"create_setup", "create_strategy"}:
            raise RuntimeError("journey_fixture_unsafe")
        diagnostic["operation"] = proposal.operation_type
        payload_hash = proposal.payload_hash
        diagnostic["stage"] = "token_issue"
        token, _ = await FinnV2ConfirmationService(session).issue_confirmation_token(
            proposal_id=proposal_id, user_id=user_id,
        )
        diagnostic["stage"] = "confirmation"
        confirmed = await FinnV2ConfirmationService(session).confirm(
            user_id=user_id,
            request=FinnV2ConfirmationRequest(
                proposal_id=proposal_id, confirmation_token=token,
                expected_payload_hash=payload_hash,
            ),
        )
        if not confirmed.confirmed:
            raise RuntimeError("journey_fixture_unsafe")
        trace["confirmed_count"] = trace.get("confirmed_count", 0) + 1
    key = f"qa-journey-execute-{uuid.uuid4().hex}"
    diagnostic["stage"] = "first_execute"
    async with async_session_factory() as session:
        try:
            executed = await FinnV2ExecutionService(session).execute(
                proposal_id=proposal_id, user_id=user_id,
                idempotency_key=key, expected_payload_hash=payload_hash,
            )
        except Exception:
            diagnostic["first_status"] = "raised"
            raise
        diagnostic["first_status"] = _safe_status(executed.status)
        diagnostic["first_codes"] = _safe_codes(getattr(executed, "error_codes", None))
    if executed.status == "succeeded":
        trace["executed_count"] = trace.get("executed_count", 0) + 1
    diagnostic["stage"] = "replay_execute"
    async with async_session_factory() as session:
        try:
            replay = await FinnV2ExecutionService(session).execute(
                proposal_id=proposal_id, user_id=user_id,
                idempotency_key=key, expected_payload_hash=payload_hash,
            )
        except Exception:
            diagnostic["replay_status"] = "raised"
            raise
        diagnostic["replay_status"] = _safe_status(replay.status)
        diagnostic["replay_codes"] = _safe_codes(getattr(replay, "error_codes", None))
    diagnostic["stage"] = "replay_check"
    diagnostic["next_step_match"] = replay.journey_next_step == executed.journey_next_step
    if (executed.status != "succeeded" or replay.status != "already_executed"
            or not diagnostic["next_step_match"]):
        raise RuntimeError("journey_replay_failed")
    return {
        "conversation_id": executed.conversation_id,
        "next_step": executed.journey_next_step,
    }


def _saved_pair(user_id: int, setup_name: str, strategy_name: str | None = None) -> dict:
    connection = fixture._connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT s.id,s.symbol,m.quote_currency FROM setups s
                              LEFT JOIN trading_markets m ON m.id=s.market_id
                              WHERE s.user_id=%s AND s.name=%s""", (user_id, setup_name))
            setups = cursor.fetchall()
            if len(setups) != 1 or setups[0][1:] != ("BTC", "USDT"):
                raise RuntimeError("journey_setup_missing")
            setup_id = int(setups[0][0])
            strategy_id = None
            if strategy_name:
                cursor.execute("""SELECT id,setup_id,symbol FROM strategies
                                  WHERE user_id=%s AND name=%s""", (user_id, strategy_name))
                strategies = cursor.fetchall()
                if (len(strategies) != 1 or strategies[0][1] != setup_id
                        or strategies[0][2] != "BTC"):
                    raise RuntimeError("journey_strategy_confirmation_failed")
                strategy_id = int(strategies[0][0])
            return {"setup_id": setup_id, "strategy_id": strategy_id}
    finally:
        connection.close()


async def _card(user_id: int, event_type: str, setup_id: int,
                strategy_id: int | None = None) -> dict:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    deadline = time.monotonic() + 45
    while True:
        async with async_session_factory() as session:
            service = FinnCoachFeedService(session)
            rows = [row for row in await service.list(user_id=user_id)
                    if row.get("event_type") == event_type]
            matches = []
            for row in rows:
                detail = await service.detail(user_id=user_id, item_id=str(row["id"]))
                evidence = (detail or {}).get("evidence") or {}
                if (str(evidence.get("setup_id")) == str(setup_id)
                        and evidence.get("trading_pair") == "BTC/USDT"
                        and (strategy_id is None or
                             str(evidence.get("strategy_id")) == str(strategy_id))):
                    if await service.detail(user_id=user_id + 1, item_id=str(row["id"])) is not None:
                        raise RuntimeError("journey_owner_scope_failed")
                    matches.append(detail)
            if len(matches) == 1:
                return matches[0]
            if len(matches) > 1:
                break
        if time.monotonic() >= deadline:
            break
        await asyncio.sleep(2)
    raise RuntimeError("journey_strategy_card_missing" if event_type == "strategy_next_step"
                       else "journey_paper_card_missing")


def _strategy_card_copy_valid(card: dict, setup_name: str) -> bool:
    title = str(card.get("title") or "").casefold()
    description = str(card.get("description") or "").casefold()
    return (card.get("status") in {"unread", "read"}
            and setup_name.casefold() in title
            and "strategie" in title and "ontbreekt" in title
            and "BTC/USDT" in str(card.get("description") or "")
            and "geen gekoppelde strategie" in description)


def _strategy_source_valid(rows: list[dict], setup_id: int, setup_name: str) -> bool:
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "completed":
            continue
        if row.get("scope") == "read_active_setup" and row.get("source") == "setups":
            data = row.get("data") or {}
            if (isinstance(data, dict) and str(data.get("setup_id")) == str(setup_id)
                    and data.get("name") == setup_name and data.get("pair") == "BTC/USDT"):
                return True
        if row.get("scope") == "read_saved_setup_inventory" and row.get("source") == "setups":
            data = row.get("data") or {}
            setups = data.get("setups") if isinstance(data, dict) else None
            if isinstance(setups, list) and any(
                isinstance(setup, dict) and str(setup.get("setup_id")) == str(setup_id)
                and setup.get("name") == setup_name and setup.get("pair") == "BTC/USDT"
                for setup in setups
            ):
                return True
    return False


def _strategy_absence_verified(rows: list[dict], setup_id: int) -> bool:
    for row in rows:
        if not isinstance(row, dict) or row.get("status") != "completed":
            continue
        data = row.get("data") or {}
        if not isinstance(data, dict):
            continue
        if (row.get("scope") == "read_linked_strategies"
                and row.get("source") == "strategies"
                and str(data.get("setup_id")) == str(setup_id)
                and data.get("complete") is True
                and data.get("strategy_count") == 0
                and data.get("strategies") == []):
            return True
        if (row.get("scope") == "read_saved_setup_inventory"
                and row.get("source") == "setups" and data.get("complete") is True):
            matches = [setup for setup in data.get("setups") or []
                       if isinstance(setup, dict)
                       and str(setup.get("setup_id")) == str(setup_id)]
            if len(matches) == 1 and matches[0].get("linked_strategies") == []:
                return True
    return False


def _current_score_evidence(rows: list[dict]) -> dict | None:
    for row in rows:
        if not isinstance(row, dict) or row.get("scope") != "read_asset_scores":
            continue
        if row.get("status") != "completed" or row.get("source") != "daily_scores_and_source_indicators":
            continue
        data = row.get("data") or {}
        if (not isinstance(data, dict) or data.get("symbol") != "BTC"
                or data.get("pair") != "BTC/USDT"
                or not isinstance(data.get("source_status"), str)):
            continue
        if data["source_status"] == "available" and (
                data.get("benchmark_score") is None or not data.get("as_of")):
            continue
        return data
    return None


async def _discuss_strategy_card(user_id: int, card: dict, setup_id: int,
                                 setup_name: str) -> dict:
    if not _strategy_card_copy_valid(card, setup_name):
        raise RuntimeError("journey_strategy_card_copy_failed")
    turn = await _turn(
        user_id,
        f"Controleer of setup {setup_name} voor BTC/USDT nog bestaat en of er inmiddels "
        "een strategie aan is gekoppeld. Zo niet, adviseer welke strategie past en "
        "welke gegevens je van mij nodig hebt. Lees ook de actuele scorestatus en "
        "noem een ontbrekende bron eerlijk. Maak niets aan.",
        feed_item_id=str(card["id"]),
    )
    content = str(turn.get("content") or "")
    if (turn.get("status") != "completed" or turn.get("proposal_id")
            or turn.get("confirmation_required") or "BTC/USDT" not in content):
        raise RuntimeError("journey_feed_discuss_failed")
    try:
        rows = await _read_tool_results(run_id=turn["run_id"],
                                        conversation_id=turn["conversation_id"],
                                        user_id=user_id)
    except RuntimeError:
        raise RuntimeError("journey_strategy_source_missing") from None
    if not _strategy_source_valid(rows, setup_id, setup_name):
        raise RuntimeError("journey_strategy_source_missing")
    if not _strategy_absence_verified(rows, setup_id):
        raise RuntimeError("journey_strategy_absence_unverified")
    score = _current_score_evidence(rows)
    if score is None:
        raise RuntimeError("journey_strategy_score_source_missing")
    if ("strategie" not in content.casefold()
            or not any(word in content.casefold() for word in
                       ("nodig", "welke", "kies", "bespreek", "voorstel", "past"))
            or not any(word in content.casefold() for word in ("score", "benchmark"))
            or (score.get("source_status") != "available" and not any(
                word in content.casefold() for word in
                ("ontbreekt", "onbekend", "niet beschikbaar", "niet verifieerbaar",
                 "verouderd", "geen actuele", "niet actueel")))
            or (score.get("source_status") == "available" and not (
                score.get("as_of") and _score_in_answer(content, str(score["benchmark_score"]))
                and _date_in_answer(content, str(score["as_of"]))))):
        raise RuntimeError("journey_strategy_advice_missing")
    return turn


async def _discuss_paper_card(user_id: int, card: dict) -> None:
    try:
        await feed_probe._discuss(
            user_id, str(card["id"]), symbol="BTC",
            question="Bespreek of voor deze BTC/USDT-strategie een Paper-bot "
                     "voorbereid kan worden. Maak er geen aan.",
            content_check=lambda answer: "BTC/USDT" in answer,
        )
    except Exception:
        raise RuntimeError("journey_feed_discuss_failed") from None


async def _wait_resolved(user_id: int, card_id: str) -> None:
    from backend.infrastructure.database import async_session_factory
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    deadline = time.monotonic() + 45
    while True:
        async with async_session_factory() as session:
            rows = await FinnCoachFeedService(session).list(user_id=user_id)
            if all(str(row["id"]) != card_id for row in rows):
                return
        if time.monotonic() >= deadline:
            raise RuntimeError("journey_strategy_card_stale")
        await asyncio.sleep(2)


async def _case(namespace: str, bound: int, trace: dict) -> dict:
    user_id = bot_id = None
    passed = False
    setup_name = f"QA BTC Setup {namespace}"
    strategy_name = f"QA BTC Strategy {namespace}"
    try:
        trace["stage"] = "seed"
        user_id, bot_id, _ = fixture._seed(namespace, bound, bot_active=False)
        baseline = _snapshot(user_id)
        if (baseline["btc_watchlist"] or baseline["active_or_live_bots"]
                or baseline["bot_orders"] or baseline["bot_executions"]
                or baseline["exchange_keys"]):
            raise RuntimeError("journey_fixture_unsafe")

        trace["stage"] = "setup_proposal"
        setup = await _turn(user_id,
            f"Ik wil los een swing-setup voor BTC/USDT op 4 uur, genaamd {setup_name}. "
            "Bereid alleen de setup voor en toon eerst het voorstel.")
        if (setup["status"] != "completed" or not setup["proposal_id"]
                or not setup["confirmation_required"]
                or setup["operation_id"] != "create_setup"
                or setup["dispatch_count"] != 1 or setup["attempt_count"] != 1):
            raise RuntimeError("journey_setup_proposal_missing")
        proposed = _snapshot(user_id)
        if any(proposed[key] != baseline[key] for key in (
                "setups", "strategies", "bot_configs", "bot_orders", "bot_executions")):
            raise RuntimeError("journey_unexpected_bot_or_order")
        trace["stage"] = "setup_confirmation"
        created_setup = await _confirm_and_execute(user_id, setup["proposal_id"], trace)
        ids = _saved_pair(user_id, setup_name)
        if (created_setup["conversation_id"] != setup["conversation_id"]
                or (created_setup["next_step"] or {}).get("step") != "strategy"
                or (created_setup["next_step"] or {}).get("setup_id") != ids["setup_id"]):
            raise RuntimeError("journey_setup_confirmation_failed")

        trace["stage"] = "setup_card"
        strategy_card = await _card(user_id, "strategy_next_step", ids["setup_id"])
        trace["stage"] = "setup_discuss"
        discussed = await _discuss_strategy_card(user_id, strategy_card,
                                                 ids["setup_id"], setup_name)
        discussion_id = discussed.get("conversation_id")
        if not discussion_id or discussion_id == setup["conversation_id"]:
            raise RuntimeError("journey_feed_lineage_failed")
        trace["stage"] = "strategy_guided"
        yes = await _turn(user_id, "ja", conversation_id=discussion_id)
        if (yes["conversation_id"] != discussion_id or
                yes["status"] not in {"completed", "clarification_required"}
                or "create_strategy" not in {yes["operation_id"], yes["guided_operation"]}
                or str(yes["supplied_inputs"].get("setup_id")) != str(ids["setup_id"])
                or yes["dispatch_count"] != 1 or yes["attempt_count"] != 1):
            raise RuntimeError("journey_strategy_guided_failed")

        trace["stage"] = "strategy_proposal"
        strategy = await _turn(user_id,
            f"Noem die strategie {strategy_name}. Vaste uitvoering van 10 euro, "
            "entry 76000 USDT, stop-loss 72000 USDT, target 83000 USDT, "
            "gebalanceerd risico. Toon eerst een voorstel, maak geen bot.",
            conversation_id=discussion_id)
        if (strategy["conversation_id"] != discussion_id
                or strategy["status"] != "completed" or not strategy["proposal_id"]
                or not strategy["confirmation_required"]
                or strategy["operation_id"] != "create_strategy"
                or str(strategy["supplied_inputs"].get("setup_id")) != str(ids["setup_id"])
                or strategy["dispatch_count"] != 1 or strategy["attempt_count"] != 1):
            raise RuntimeError("journey_strategy_proposal_missing")
        proposed = _snapshot(user_id)
        if (proposed["setups"] != baseline["setups"] + 1
                or proposed["strategies"] != baseline["strategies"]
                or any(proposed[key] != baseline[key] for key in (
                    "bot_configs", "bot_orders", "bot_executions"))):
            raise RuntimeError("journey_unexpected_bot_or_order")
        trace["stage"] = "strategy_confirmation"
        created_strategy = await _confirm_and_execute(user_id, strategy["proposal_id"], trace)
        ids = _saved_pair(user_id, setup_name, strategy_name)
        if (created_strategy["conversation_id"] != discussion_id
                or (created_strategy["next_step"] or {}).get("step") != "paper"
                or (created_strategy["next_step"] or {}).get("setup_id") != ids["setup_id"]
                or (created_strategy["next_step"] or {}).get("strategy_id") != ids["strategy_id"]):
            raise RuntimeError("journey_strategy_confirmation_failed")
        trace["stage"] = "paper_card"
        paper_card = await _card(user_id, "paper_next_step", ids["setup_id"],
                                 ids["strategy_id"])
        await _wait_resolved(user_id, str(strategy_card["id"]))
        trace["stage"] = "paper_discuss"
        await _discuss_paper_card(user_id, paper_card)
        trace["stage"] = "paper_guided"
        paper_yes = await _turn(user_id, "ja", conversation_id=discussion_id)
        if (paper_yes["conversation_id"] != discussion_id
                or paper_yes["status"] not in {"completed", "clarification_required"}
                or paper_yes["proposal_id"]
                or "create_bot" not in {paper_yes["operation_id"], paper_yes["guided_operation"]}
                or str(paper_yes["supplied_inputs"].get("strategy_id")) != str(ids["strategy_id"])
                or paper_yes["dispatch_count"] != 1 or paper_yes["attempt_count"] != 1):
            raise RuntimeError("journey_paper_guided_failed")

        trace["stage"] = "safety"
        after = _snapshot(user_id)
        if (trace.get("confirmed_count") != 2 or trace.get("executed_count") != 2
                or after["setups"] != baseline["setups"] + 1
                or after["strategies"] != baseline["strategies"] + 1
                or any(after[key] != baseline[key] for key in (
                    "bot_configs", "bot_orders", "bot_executions", "exchange_keys",
                    "active_or_live_bots", "btc_watchlist"))):
            raise RuntimeError("journey_unexpected_bot_or_order")
        passed = True
        return {"result": "PASS", "setup_confirmation": True,
                "strategy_confirmation": True, "setup_lineage": True,
                "strategy_card": bool(strategy_card), "paper_card": bool(paper_card),
                "feed_discussions": True, "feed_strategy_lineage": True,
                "strategy_source_verified": True, "short_yes_continuity": True, "replay": True,
                "no_watchlist_required": True, "no_bot_or_order": True}
    finally:
        if user_id is not None and bot_id is not None:
            trace["stage_before_cleanup"] = trace["stage"]
            trace["stage"] = "cleanup"
            try:
                if passed:
                    fixture._cleanup(namespace, user_id, bot_id,
                                     require_safe_pair_cleanup=True)
                    trace["fixture_state"] = "cleaned"
                else:
                    fixture._quarantine(namespace, user_id, bot_id)
                    trace["fixture_state"] = "quarantined"
            except Exception:
                trace["fixture_state"] = "cleanup_failed"
                raise RuntimeError("journey_cleanup_failed") from None


def run(namespace: str) -> dict:
    bound = _bound_owner(namespace)
    from backend.infrastructure.database import engine
    from backend.scripts.probe_protected_paper_exit_reconciliation import _guard_live_exchange

    trace = {"stage": "seed", "fixture_state": "not_created"}
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        with _guard_live_exchange() as live_attempts:
            try:
                result = loop.run_until_complete(_case(namespace, bound, trace))
                result["fixture_state"] = trace["fixture_state"]
            except Exception as error:
                code = str(error)
                result = {"result": "FAIL",
                          "reason": code if code in FAILURES else "journey_runtime_failed",
                          "failure_stage": trace.get("stage_before_cleanup", trace["stage"]),
                          "fixture_state": trace["fixture_state"]}
            if "execution_diagnostic" in trace:
                result["execution_diagnostic"] = trace["execution_diagnostic"].copy()
            result["live_calls"] = len(live_attempts)
            result["fixture_executions"] = trace.get("executed_count", 0)
            result["fixture_confirmations"] = trace.get("confirmed_count", 0)
            if live_attempts:
                result["result"] = "FAIL"
                result["reason"] = "journey_unexpected_bot_or_order"
            return result
    finally:
        loop.run_until_complete(engine.dispose())
        loop.close()
        asyncio.set_event_loop(None)
