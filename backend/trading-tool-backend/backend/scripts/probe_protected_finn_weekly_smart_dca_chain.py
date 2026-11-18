"""Protected FINN-created weekly Smart DCA plan through one Paper purchase."""

from __future__ import annotations

import os
import secrets
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from backend.scripts import probe_protected_manual_trade_temporary_matrix as temporary
from backend.scripts import probe_protected_weekly_smart_dca_paper as weekly
from backend.scripts import probe_protected_score2_stale_paper as fixture


PROFILE_FLAG = "FINN_QA_ALLOW_FINN_WEEKLY_CHAIN_FIXTURE"
PLAN_NAME_PREFIX = "Smart DCA"


def _require_protected_run(namespace: str) -> int:
    if os.getenv(PROFILE_FLAG) != "1":
        raise RuntimeError("finn_weekly_chain_fixture_not_authorized")
    return weekly._require_protected_run(namespace)


def _issue_child_token(child: int, issuer: Path) -> str:
    from backend.scripts.run_finn_production_qa import issue_fixture_token

    original = {key: os.environ.get(key) for key in ("FINN_QA_USER_ID", "FINN_QA_TEMP_CHILD_RUN")}
    os.environ["FINN_QA_USER_ID"] = str(child)
    os.environ["FINN_QA_TEMP_CHILD_RUN"] = "1"
    try:
        return issue_fixture_token(issuer=issuer)
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _chat_create_plan(base_url: str, child_token: str, parent_token: str,
                      child: int, namespace: str, market_id: int) -> tuple[int, int, dict]:
    from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
    from backend.scripts.run_finn_v2_full_action_matrix import _proposal_lifecycle, _runtime_record
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan

    name = f"{PLAN_NAME_PREFIX} {namespace}"
    try:
        first = run_gate(
            base_url=base_url, bearer_token=child_token, timeout_seconds=100,
            message=(f"Ik wil een BTC/USDT DCA-setup met de naam {name}, tijdframe 1D. "
                     "Elke week hooguit één aankoop, maar geen vaste weekdag. "
                     "Mijn basisbedrag is €200. Laat het bedrag meebewegen met de gezamenlijke "
                     "benchmark van Markt, Macro en Technisch: 150% bij een zwakke score, "
                     "100% bij een middenscore en 50% bij een sterke score. "
                     "Ik wil eerst een concept, nog geen bot of order."),
        )
    except (AssertionError, TimeoutError) as error:
        raise RuntimeError("finn_weekly_chain_first_turn_transport_failed") from error
    if first["status"] != "clarification_required" or first["final_operation_id"] != "create_setup":
        raise RuntimeError("finn_weekly_chain_guided_state_wrong")
    first_state = _runtime_record(first["run_id"])["runtime_state"]
    if set((first_state.get("guided_state") or {}).get("missing_required_inputs") or []) != {
        "low_threshold", "high_threshold",
    }:
        raise RuntimeError("finn_weekly_chain_guided_inputs_wrong")
    try:
        second = run_gate(
            base_url=base_url, bearer_token=child_token, timeout_seconds=100,
            conversation_id=first["conversation_id"],
            message=("Mijn scoregrenzen zijn: onder 26 zwak (€300), 26 tot en met 75 midden "
                     "(€200), vanaf 76 sterk (€100). Dat is 150/100/50 procent van €200. "
                     "Maak de bevestigbare BTC/USDT-setup en gekoppelde strategie voor dit "
                     "wekelijkse plan zonder vaste dag. Maak nog geen bot en koop niets."),
        )
    except (AssertionError, TimeoutError) as error:
        raise RuntimeError("finn_weekly_chain_second_turn_transport_failed") from error
    record = _runtime_record(second["run_id"])
    proposal = record["proposal"]
    if (second["status"] != "completed" or second["final_operation_id"] != "create_setup"
            or not proposal or proposal["operation_type"] != "create_setup"):
        raise RuntimeError("finn_weekly_chain_proposal_missing")
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT payload_json FROM finn_v2_proposals WHERE id=%s AND run_id=%s",
                        (proposal["id"], second["run_id"]))
            row = cur.fetchone()
        payload = row[0] if row and isinstance(row[0], dict) else {}
        fields = dict((payload.get("change") or {}).get("setup_fields") or {})
    finally:
        conn.close()
    expected = {
        "symbol": "BTC", "quote_currency": "USDT", "dca_frequency": "weekly",
        "dca_trigger_mode": "benchmark", "dca_amount_mode": "score_bands",
        "dca_day": None, "base_amount": 200, "low_threshold": 26,
        "high_threshold": 76, "low_score_percent": 150,
        "mid_score_percent": 100, "high_score_percent": 50,
    }
    if any(fields.get(key) != value for key, value in expected.items()):
        raise RuntimeError("finn_weekly_chain_proposal_fields_wrong")
    _, expected_strategy = split_confirmed_dca_plan({"setup_type": "dca", "name": name, **expected})
    try:
        lifecycle = _proposal_lifecycle(base_url, child_token, parent_token, proposal)
    except (AssertionError, RuntimeError, TimeoutError) as error:
        raise RuntimeError("finn_weekly_chain_proposal_lifecycle_failed") from error
    if not (lifecycle["cross_user_rejected"]
            and lifecycle["publish_status"] == lifecycle["confirmation_status"] == 200
            and lifecycle["confirmed"] and lifecycle["execution_status"] == 200
            and lifecycle["execution_result"] == "succeeded"
            and lifecycle["idempotency_replay_status"] == 200
            and lifecycle["idempotency_result"] == "already_executed"):
        raise RuntimeError("finn_weekly_chain_confirmation_or_replay_failed")
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT s.id,s.symbol,s.market_id,s.timeframe,s.setup_type,
                          s.dca_frequency,s.dca_trigger_mode,s.dca_day,s.dca_month_day,
                          st.id,st.setup_id,st.symbol,st.market_id,st.execution_mode,
                          st.base_amount,st.decision_curve,st.data
                   FROM setups s JOIN strategies st ON st.setup_id=s.id AND st.user_id=s.user_id
                   WHERE s.user_id=%s AND s.name=%s ORDER BY st.id""",
                (child, name),
            )
            saved = cur.fetchall()
            cur.execute("SELECT COUNT(*) FROM bot_configs WHERE user_id=%s",
                        (child,))
            bot_count = cur.fetchone()[0]
        if len(saved) != 1 or bot_count:
            raise RuntimeError("finn_weekly_chain_saved_plan_cardinality_wrong")
        row = saved[0]
        if (row[1:9] != ("BTC", market_id, "1D", "dca", "weekly", "benchmark", None, None)
                or row[10] != row[0] or row[11:14] != ("BTC", market_id, "custom")
                or float(row[14]) != 200.0 or row[15] != expected_strategy["decision_curve"]
                or (row[16] or {}).get("dca_amount_semantics") != "planned_exact"):
            raise RuntimeError("finn_weekly_chain_saved_plan_wrong")
        return int(row[0]), int(row[9]), {
            "first_run_id": first["run_id"], "proposal_run_id": second["run_id"],
            "proposal_confirmed": True, "replay": "already_executed",
            "owner_isolation": True,
        }
    finally:
        conn.close()


def _seed_paper_bot(child: int, strategy_id: int, market_id: int, namespace: str) -> int:
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    observed = now - timedelta(hours=1)
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE id=%s", (child,))
            if cur.fetchone() != (False,):
                raise RuntimeError("finn_weekly_chain_owner_not_deactivated")
            cur.execute(
                """SELECT s.id FROM strategies st JOIN setups s ON s.id=st.setup_id
                   WHERE st.id=%s AND st.user_id=%s AND s.user_id=%s
                     AND st.market_id=%s AND s.market_id=%s""",
                (strategy_id, child, child, market_id, market_id),
            )
            if not cur.fetchone():
                raise RuntimeError("finn_weekly_chain_strategy_link_missing")
            cur.execute(
                """INSERT INTO bot_configs
                   (user_id,strategy_id,cadence,symbol,market_id,name,mode,is_live,is_active,
                    risk_profile,budget_total_eur,budget_daily_limit_eur,budget_min_order_eur,
                    budget_max_order_eur,max_asset_exposure_pct,base_currency,
                    paper_initial_cash_eur,created_at,updated_at)
                   VALUES (%s,%s,'weekly','BTC',%s,%s,'auto',FALSE,TRUE,'balanced',
                           1000,300,1,300,100,'EUR',1000,%s,%s) RETURNING id""",
                (child, strategy_id, market_id, namespace, now, now),
            )
            bot_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_portfolios
                   (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,realized_pnl_eur)
                   VALUES (%s,%s,'BTC',1000,0,0,0)""", (bot_id, child),
            )
            for category, indicator, value, table, column in (
                ("macro", "dxy", 102.2, "macro_data", "name"),
                ("technical", "rsi", 55, "technical_indicators", "indicator"),
                ("market", "change_24h", 1.5, "market_data_indicators", "name"),
            ):
                scoped_market = market_id if category != "macro" else None
                cur.execute(
                    """INSERT INTO user_indicator_configs
                       (user_id,indicator,category,symbol,asset_class,priority,enabled,
                        created_at,updated_at,market_id)
                       VALUES (%s,%s,%s,'BTC','crypto',1,TRUE,%s,%s,%s)""",
                    (child, indicator, category, now - timedelta(hours=3),
                     now - timedelta(hours=3), scoped_market),
                )
                if category == "macro":
                    cur.execute(
                        """INSERT INTO macro_data
                           (user_id,symbol,name,value,timestamp,source_observed_at)
                           VALUES (%s,'BTC',%s,%s,%s,%s)""",
                        (child, indicator, value, observed, observed),
                    )
                else:
                    cur.execute(
                        f"""INSERT INTO {table}
                           (user_id,symbol,{column},value,timestamp,source_observed_at,market_id)
                           VALUES (%s,'BTC',%s,%s,%s,%s,%s)""",
                        (child, indicator, value, observed, observed, scoped_market),
                    )
            for days_ago, dxy in ((4, 101.5), (3, 101.7), (2, 101.9), (1, 102.1)):
                day = observed - timedelta(days=days_ago)
                cur.execute(
                    """INSERT INTO macro_data
                       (user_id,symbol,name,value,timestamp,source_observed_at)
                       VALUES (%s,'BTC','dxy',%s,%s,%s)""",
                    (child, dxy, day, day),
                )
        conn.commit()
        return bot_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _assert_bot_link(child: int, bot_id: int, setup_id: int, strategy_id: int) -> None:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT b.strategy_id,st.setup_id,b.is_live
                   FROM bot_configs b JOIN strategies st
                     ON st.id=b.strategy_id AND st.user_id=b.user_id
                   WHERE b.id=%s AND b.user_id=%s""", (bot_id, child),
            )
            row = cur.fetchone()
        if row != (strategy_id, setup_id, False):
            raise RuntimeError("finn_weekly_chain_bot_strategy_link_wrong")
    finally:
        conn.close()


def _run_paper(child: int, bot_id: int, market_id: int, first: date, second: date) -> dict:
    from backend.celery_task.store_daily_scores_task import build_daily_scores_for_market
    from backend.engine.trading_bot_execution import run_trading_bot_execution

    result = build_daily_scores_for_market(child, market_id)
    if any(score is None for score in result["scores"].values()):
        raise RuntimeError("finn_weekly_chain_scores_incomplete")
    first_result = run_trading_bot_execution(child, report_date=first, bot_id=bot_id, paper_only=True)
    if not first_result.get("ok") or len(first_result.get("decisions") or []) != 1:
        raise RuntimeError("finn_weekly_chain_first_assessment_failed")
    for day, code in ((first, "same_day"), (second, "same_week")):
        if day == second:
            weekly._copy_score_for_second_day(child, market_id, first, second)
        repeat = run_trading_bot_execution(child, report_date=day, bot_id=bot_id, paper_only=True)
        if (not repeat.get("ok") or repeat.get("decisions")
                or (repeat.get("skip_reasons") or {}).get(bot_id) != "already_pending_or_executed"):
            raise RuntimeError(f"finn_weekly_chain_{code}_not_blocked")
    return weekly._verify(child, bot_id, market_id, first, second)


def _cleanup(child: int, namespace: str) -> None:
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_active,ai_preferences FROM users WHERE id=%s FOR UPDATE", (child,))
            row = cur.fetchone()
            lease = (row[1] or {}).get("finn_temp_qa") if row else None
            if (not row or row[0] is not False
                    or (row[1] or {}).get("qa_fixture") != temporary.FINN_TEMP_QA_KIND
                    or not isinstance(lease, dict) or lease.get("namespace") != namespace
                    or lease.get("status") != "revoked"):
                raise RuntimeError("finn_weekly_chain_cleanup_binding_wrong")
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (child,))
            if cur.fetchone()[0]:
                raise RuntimeError("finn_weekly_chain_cleanup_exchange_key_present")
            cur.execute("SELECT id,is_live FROM bot_configs WHERE user_id=%s FOR UPDATE", (child,))
            bots = cur.fetchall()
            if len(bots) > 1 or any(is_live for _, is_live in bots):
                raise RuntimeError("finn_weekly_chain_cleanup_bot_unsafe")
            cur.execute("SELECT COUNT(*) FROM bot_orders WHERE user_id=%s AND execution_environment IS DISTINCT FROM 'paper'", (child,))
            if cur.fetchone()[0]:
                raise RuntimeError("finn_weekly_chain_cleanup_live_order_present")
            cur.execute("UPDATE bot_configs SET is_active=FALSE WHERE user_id=%s AND is_live=FALSE", (child,))
            for table in (
                "bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
                "bot_decisions", "portfolio_value_snapshots_v2", "bot_portfolio_snapshots",
                "portfolio_balance_snapshots", "bot_portfolios", "bot_configs", "strategies",
            ):
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()[0] is not None:
                    cur.execute(f"DELETE FROM {table} WHERE user_id=%s", (child,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    temporary._db(temporary._delete_child(child, namespace))
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            for table, column in (
                ("users", "id"), ("finn_v2_conversations", "user_id"),
                ("finn_v2_runs", "user_id"), ("finn_v2_proposals", "user_id"),
                ("setups", "user_id"), ("strategies", "user_id"),
                ("bot_configs", "user_id"), ("bot_orders", "user_id"),
            ):
                cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {column}=%s", (child,))
                if cur.fetchone()[0]:
                    raise RuntimeError("finn_weekly_chain_cleanup_rows_remain")
    finally:
        conn.close()


async def _parent_hash(parent: int) -> str:
    from backend.infrastructure.database import async_session_factory

    async with async_session_factory() as session:
        return await temporary._parent_state(session, parent)


def run(namespace: str, *, base_url: str, parent_token: str, issuer: Path) -> dict:
    parent = _require_protected_run(namespace)
    market_id = weekly._source()
    first = datetime.now(ZoneInfo("Europe/Amsterdam")).date()
    second = weekly._next_same_week(first)
    conn = fixture._connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT CURRENT_DATE")
            if cur.fetchone()[0] != first:
                raise RuntimeError("finn_weekly_chain_date_boundary_unavailable")
    finally:
        conn.close()
    child = None
    revoked = False
    try:
        lease_secret = secrets.token_urlsafe(32)
        child, parent_hash = temporary._db(temporary._create_child(parent, namespace, lease_secret))
        temporary._db(temporary._extend_lease(child, namespace, lease_secret))
        child_token = _issue_child_token(child, issuer)
        setup_id, strategy_id, chat = _chat_create_plan(
            base_url, child_token, parent_token, child, namespace, market_id,
        )
        del child_token
        temporary._db(temporary._revoke_child(child, namespace))
        revoked = True
        bot_id = _seed_paper_bot(child, strategy_id, market_id, namespace)
        _assert_bot_link(child, bot_id, setup_id, strategy_id)
        result = _run_paper(child, bot_id, market_id, first, second)
        _assert_bot_link(child, bot_id, setup_id, strategy_id)
    finally:
        if child is not None:
            if not revoked:
                temporary._db(temporary._revoke_child(child, namespace))
            _cleanup(child, namespace)
    if temporary._db(_parent_hash(parent)) != parent_hash:
        raise RuntimeError("finn_weekly_chain_parent_state_changed")
    return {**result, **chat, "saved_setup_strategy_link": True,
            "bot_strategy_link": True, "cleanup_verified": True}
