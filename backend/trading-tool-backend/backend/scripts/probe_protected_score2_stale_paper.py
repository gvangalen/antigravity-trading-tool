"""One-shot, protected production QA probe for stale Score 2.0 Paper safety.

Only the protected QA runner may call this module. It creates an isolated,
uncredentialed fixture owner, never changes shared market data, and removes
its rows after reading the persisted decision. The report contains no IDs.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timedelta, timezone

FIXTURE_MARKER = "finn_score2_stale_paper_qa_v1"
QA_OWNER_MARKER = "finn_production_qa_v1"
NAMESPACE_PATTERN = re.compile(r"qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8}\Z")


def _require_protected_run(namespace: str) -> int:
    if os.getenv("FINN_QA_ALLOW_STALE_SCORE_FIXTURE") != "1":
        raise RuntimeError("stale_fixture_not_authorized")
    if not NAMESPACE_PATTERN.fullmatch(namespace):
        raise RuntimeError("stale_fixture_namespace_invalid")
    bound = os.getenv("FINN_QA_USER_ID", "")
    if not bound.isdecimal() or int(bound) <= 0:
        raise RuntimeError("fixture_binding_invalid")
    return int(bound)


def _connection():
    from backend.utils.db import get_db_connection

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("qa_database_unavailable")
    return conn


def _seed(namespace: str, bound_qa_owner: int) -> tuple[int, int, str]:
    from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
    from backend.utils.auth_utils import hash_password

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    fresh = now - timedelta(hours=1)
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role,is_active,ai_preferences FROM users WHERE id=%s",
                (bound_qa_owner,),
            )
            qa = cur.fetchone()
            if not qa or qa[0] != "user" or qa[1] is not True or (qa[2] or {}).get("qa_fixture") != QA_OWNER_MARKER:
                raise RuntimeError("fixture_binding_invalid")
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (bound_qa_owner,))
            if cur.fetchone()[0]:
                raise RuntimeError("fixture_has_exchange_keys")
            cur.execute(
                """INSERT INTO users (email,password_hash,role,is_active,ai_preferences)
                   VALUES (%s,%s,'user',FALSE,%s::jsonb) RETURNING id""",
                (
                    f"score2-stale-{namespace}@tradamind.example",
                    hash_password(secrets.token_urlsafe(48)),
                    json.dumps({"qa_fixture": FIXTURE_MARKER, "qa_namespace": namespace}),
                ),
            )
            user_id = int(cur.fetchone()[0])
            cur.execute("SELECT CURRENT_DATE")
            report_date = cur.fetchone()[0].isoformat()
            cur.execute(
                """INSERT INTO setups
                   (user_id,name,symbol,timeframe,setup_type,dca_frequency,
                    min_benchmark_score,max_benchmark_score,created_at,last_validated)
                   VALUES (%s,%s,'ETH','1D','dca','daily',0,100,%s,%s) RETURNING id""",
                (user_id, namespace, now, now),
            )
            setup_id = int(cur.fetchone()[0])
            _, strategy = split_confirmed_dca_plan({
                "setup_type": "dca", "name": namespace, "base_amount": 10,
                "dca_amount_mode": "score_bands", "score_source": "benchmark_score",
                "low_threshold": 40, "high_threshold": 70,
                "low_score_percent": 50, "mid_score_percent": 100,
                "high_score_percent": 150,
            })
            cur.execute(
                """INSERT INTO strategies
                   (user_id,setup_id,name,symbol,timeframe,setup_type,execution_mode,
                    base_amount,decision_curve,data,created_at)
                   VALUES (%s,%s,%s,'ETH','1D','dca','custom',%s,%s::jsonb,%s::jsonb,%s)
                   RETURNING id""",
                (user_id, setup_id, namespace, strategy["base_amount"],
                 json.dumps(strategy["decision_curve"]),
                 json.dumps({"dca_amount_semantics": "planned_exact"}), now),
            )
            strategy_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_configs
                   (user_id,strategy_id,cadence,symbol,name,mode,is_live,is_active,
                    risk_profile,budget_total_eur,budget_daily_limit_eur,
                    budget_min_order_eur,budget_max_order_eur,max_asset_exposure_pct,
                    base_currency,paper_initial_cash_eur,created_at,updated_at)
                   VALUES (%s,%s,'daily','ETH',%s,'manual',FALSE,TRUE,'balanced',
                           100,100,1,20,100,'EUR',100,%s,%s) RETURNING id""",
                (user_id, strategy_id, namespace, now, now),
            )
            bot_id = int(cur.fetchone()[0])
            cur.execute(
                """INSERT INTO bot_portfolios
                   (bot_id,user_id,symbol,cash_eur,position_qty,invested_eur,realized_pnl_eur)
                   VALUES (%s,%s,'ETH',100,0,0,0)""",
                (bot_id, user_id),
            )
            for category, name, value, observed, table, name_column in (
                ("macro", "dxy", 102.2, fresh, "macro_data", "name"),
                ("technical", "rsi", 55, fresh, "technical_indicators", "indicator"),
                ("market", "change_24h", 1.5, fresh, "market_data_indicators", "name"),
            ):
                cur.execute(
                    """INSERT INTO user_indicator_configs
                       (user_id,indicator,category,symbol,asset_class,priority,enabled,created_at,updated_at)
                       VALUES (%s,%s,%s,'ETH','crypto',1,TRUE,%s,%s)""",
                    (user_id, name, category, now - timedelta(hours=3), now - timedelta(hours=3)),
                )
                cur.execute(
                    f"""INSERT INTO {table}
                       (user_id,symbol,{name_column},value,timestamp,source_observed_at)
                       VALUES (%s,'ETH',%s,%s,%s,%s)""",
                    (user_id, name, value, observed, observed),
                )
            for days_ago, dxy in ((4, 101.5), (3, 101.7), (2, 101.9), (1, 102.1)):
                observed = fresh - timedelta(days=days_ago)
                cur.execute(
                    """INSERT INTO macro_data
                       (user_id,symbol,name,value,timestamp,source_observed_at)
                       VALUES (%s,'ETH','dxy',%s,%s,%s)""",
                    (user_id, dxy, observed, observed),
                )
        conn.commit()
        return user_id, bot_id, report_date
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _verify(user_id: int, bot_id: int, report_date: str) -> dict:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT macro_score,technical_score,market_score,indicator_evidence
                   FROM daily_scores WHERE user_id=%s AND symbol='ETH' AND report_date=%s""",
                (user_id, report_date),
            )
            score = cur.fetchone()
            cur.execute(
                """SELECT action,amount_eur,scores_json,status
                   FROM bot_decisions WHERE user_id=%s AND bot_id=%s AND decision_date=%s""",
                (user_id, bot_id, report_date),
            )
            decision = cur.fetchone()
            cur.execute("SELECT COUNT(*) FROM bot_orders WHERE user_id=%s AND bot_id=%s", (user_id, bot_id))
            orders = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM bot_ledger WHERE user_id=%s AND bot_id=%s", (user_id, bot_id))
            ledger = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM exchange_keys WHERE user_id=%s", (user_id,))
            keys = cur.fetchone()[0]
            cur.execute("SELECT is_active FROM users WHERE id=%s", (user_id,))
            owner_active = cur.fetchone()[0]
            cur.execute(
                """SELECT p.cash_eur,b.is_active,b.is_live,b.mode
                   FROM bot_portfolios p JOIN bot_configs b ON b.id=p.bot_id
                   WHERE p.user_id=%s AND p.bot_id=%s AND p.symbol='ETH'""",
                (user_id, bot_id),
            )
            state = cur.fetchone()
            cur.execute(
                """SELECT source_observed_at FROM market_data_indicators
                   WHERE user_id=%s AND symbol='ETH' AND name='change_24h'
                   ORDER BY source_observed_at DESC LIMIT 1""",
                (user_id,),
            )
            reading = cur.fetchone()
        from backend.utils.scoring_utils import score_source_is_fresh

        if not reading or score_source_is_fresh("market", "change_24h", reading[0], symbol="ETH"):
            raise RuntimeError("fixture_raced_with_refresh")
        if not score or score[0] is None or score[1] is None or score[2] is not None:
            raise RuntimeError("score_components_unexpected")
        evidence = score[3] or {}
        if not isinstance(evidence, dict) or "change_24h" in (evidence.get("market") or {}):
            raise RuntimeError("stale_source_laundered")
        if not decision:
            raise RuntimeError("paper_decision_missing")
        action, amount, payload, status = decision
        _assert_stale_paper_contract(
            action=action, amount=amount, payload=payload, orders=orders,
            ledger=ledger, keys=keys, owner_active=owner_active, state=state,
        )
        return {
            "result": "PASS", "score_components": "macro_and_technical_only",
            "stale_component": "market_change_24h", "setup_match": "insufficient_data",
            "decision": "hold", "amount_eur": 0, "orders": 0,
            "ledger_entries": 0, "paper_cash_unchanged": True,
            "live_bot": False, "decision_status": status,
        }
    finally:
        conn.close()


def _assert_stale_paper_contract(*, action, amount, payload, orders, ledger,
                                 keys, owner_active, state) -> None:
    """Emit only a failed invariant code, never protected fixture contents."""
    if action != "hold" or amount is None or float(amount) != 0:
        raise RuntimeError("stale_paper_decision_not_hold_zero")
    if not isinstance(payload, dict) or (payload.get("setup_match") or {}).get("status") != "insufficient_data":
        raise RuntimeError("stale_paper_setup_match_not_insufficient")
    policy = payload.get("dca_policy") or {}
    if policy.get("source_available") is not False or policy.get("source_score") is not None:
        raise RuntimeError("stale_paper_dca_policy_not_unavailable")
    if orders != 0 or ledger != 0:
        raise RuntimeError("stale_paper_execution_side_effect")
    if keys != 0 or owner_active is not False:
        raise RuntimeError("stale_paper_fixture_safety_breach")
    if not state or float(state[0]) != 100 or state[1] is not True or state[2] is not False or state[3] != "manual":
        raise RuntimeError("stale_paper_bot_state_changed")


def _age_market_reading(user_id: int) -> None:
    """Prove the rule scores when fresh, then make that same source stale."""
    from backend.utils.scoring_utils import generate_scores_db

    fresh = generate_scores_db("market", user_id=user_id, symbol="ETH")
    component = (fresh.get("scores") or {}).get("change_24h") or {}
    if (fresh.get("total_score") is None
            or component.get("rule_origin") not in {"custom", "system_template"}):
        raise RuntimeError("fresh_control_score_missing")
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE market_data_indicators
                   SET source_observed_at=NOW()-INTERVAL '30 days',
                       timestamp=NOW()-INTERVAL '30 days'
                   WHERE user_id=%s AND symbol='ETH' AND name='change_24h'""",
                (user_id,),
            )
            if cur.rowcount != 1:
                raise RuntimeError("stale_fixture_source_missing")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    aged = generate_scores_db("market", user_id=user_id, symbol="ETH")
    if aged.get("source_status") != "missing_or_stale_indicator" or aged.get("total_score") is not None:
        raise RuntimeError("stale_control_score_unexpected")


def _cleanup(namespace: str, user_id: int, bot_id: int) -> None:
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT ai_preferences FROM users WHERE id=%s FOR UPDATE""",
                (user_id,),
            )
            row = cur.fetchone()
            if not row or (row[0] or {}).get("qa_fixture") != FIXTURE_MARKER or (row[0] or {}).get("qa_namespace") != namespace:
                raise RuntimeError("fixture_cleanup_owner_mismatch")
            cur.execute("UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE", (bot_id, user_id))
            if cur.rowcount != 1:
                raise RuntimeError("fixture_cleanup_bot_mismatch")
            for table in (
                "bot_trade_plans", "bot_executions", "bot_ledger", "bot_orders",
                "bot_decisions", "bot_portfolio_snapshots", "portfolio_balance_snapshots",
                "bot_portfolios", "bot_configs", "strategies", "setups", "daily_scores",
                "macro_data", "technical_indicators", "market_data_indicators",
                "user_indicator_configs",
            ):
                cur.execute("SELECT to_regclass(%s)", (f"public.{table}",))
                if cur.fetchone()[0] is not None:
                    cur.execute(f"DELETE FROM {table} WHERE user_id=%s", (user_id,))
            cur.execute("DELETE FROM users WHERE id=%s", (user_id,))
            if cur.rowcount != 1:
                raise RuntimeError("fixture_cleanup_user_missing")
        conn.commit()
    except Exception:
        conn.rollback()
        # A failed cleanup must still disable the Paper bot.
        with conn.cursor() as cur:
            cur.execute("UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE", (bot_id, user_id))
        conn.commit()
        raise RuntimeError("fixture_cleanup_failed") from None
    finally:
        conn.close()


def _quarantine(namespace: str, user_id: int, bot_id: int) -> None:
    """Disable the bot but retain a failed run's private evidence for QA."""
    conn = _connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT ai_preferences FROM users WHERE id=%s FOR UPDATE", (user_id,))
            row = cur.fetchone()
            if not row or (row[0] or {}).get("qa_fixture") != FIXTURE_MARKER or (row[0] or {}).get("qa_namespace") != namespace:
                raise RuntimeError("fixture_quarantine_owner_mismatch")
            cur.execute(
                "UPDATE bot_configs SET is_active=FALSE WHERE id=%s AND user_id=%s AND is_live=FALSE",
                (bot_id, user_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("fixture_quarantine_bot_mismatch")
        conn.commit()
    except Exception:
        conn.rollback()
        raise RuntimeError("fixture_quarantine_failed") from None
    finally:
        conn.close()


def run(namespace: str) -> dict:
    bound = _require_protected_run(namespace)
    user_id = bot_id = None
    output = None
    verified = False
    try:
        user_id, bot_id, report_date = _seed(namespace, bound)
        _age_market_reading(user_id)
        from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user
        from backend.engine.trading_bot_execution import run_trading_bot_execution

        build_daily_scores_for_user(user_id, ["ETH"])
        from datetime import date

        result = run_trading_bot_execution(
            user_id, report_date=date.fromisoformat(report_date),
            bot_id=bot_id, paper_only=True,
        )
        if not result.get("ok") or len(result.get("decisions") or []) != 1:
            raise RuntimeError("paper_assessment_failed")
        output = _verify(user_id, bot_id, report_date)
        verified = True
    finally:
        if user_id is not None and bot_id is not None:
            if verified:
                _cleanup(namespace, user_id, bot_id)
            else:
                _quarantine(namespace, user_id, bot_id)
    return output
