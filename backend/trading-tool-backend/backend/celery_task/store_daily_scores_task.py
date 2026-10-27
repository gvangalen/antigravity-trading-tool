import logging
import json
import math
import os
from celery import shared_task

from backend.utils.db import get_db_connection
from backend.utils.scoring_utils import generate_scores_db

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RULE_BASED_SCORES_LEASE_KEY = "task-lease:run_rule_based_daily_scores"
RULE_BASED_SCORES_LEASE_SECONDS = 30 * 60
SCORE_OWNER_LOCK_NAMESPACE = 271024


def _jsonb(value):
    """Zorgt dat we altijd geldige JSON naar jsonb casten."""
    return json.dumps(value or [], ensure_ascii=False)


def _confirmed_component_score(result):
    """Do not persist the score engine's display fallback as trading evidence."""
    score = result.get("total_score")
    contributions = result.get("scores") or {}
    if not isinstance(contributions, dict) or type(score) not in {int, float} or not math.isfinite(score):
        return None
    if not 0 <= score <= 100:
        return None
    if not any(
        isinstance(entry, dict)
        and type(entry.get("weight")) in {int, float}
        and math.isfinite(entry["weight"])
        and entry["weight"] > 0
        for entry in contributions.values()
    ):
        return None
    return score


def _broker_client():
    broker_url = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
    import redis

    return redis.from_url(broker_url, socket_connect_timeout=1, socket_timeout=1)


def _try_acquire_rule_based_scores_lease() -> object | None:
    try:
        client = _broker_client()
        acquired = bool(
            client.set(
                RULE_BASED_SCORES_LEASE_KEY,
                "1",
                nx=True,
                ex=RULE_BASED_SCORES_LEASE_SECONDS,
            )
        )
        if acquired:
            return client
        client.close()
    except Exception as exc:
        logger.warning("⚠️ Kon rule-based-scores lease niet claimen: %s", exc)
    return None


def _release_rule_based_scores_lease(client) -> None:
    if client is None:
        return
    try:
        client.delete(RULE_BASED_SCORES_LEASE_KEY)
    except Exception as exc:
        logger.warning("⚠️ Kon rule-based-scores lease niet vrijgeven: %s", exc)
    finally:
        try:
            client.close()
        except Exception:
            pass


# =========================================================
# 1️⃣ BUILD DAILY SCORES (RULE-BASED) — PER USER
# =========================================================
def build_daily_scores_for_user(user_id: int, symbols: list[str] | None = None):
    """
    Bouwt daily_scores voor de assets in de watchlist van de user.
    """
    logger.info(f"🧮 Daily scores bouwen voor watchlist van user_id={user_id}")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    saved_symbols = []
    try:
        # The periodic sweep, onboarding, history repair and market-refresh
        # handoff all write the same daily score row. Serialize them per owner
        # before reading any sources, through the final UPSERT/commit, so an
        # older calculation cannot finish after and replace newer evidence.
        # A session lock survives the commits below and is released when this
        # dedicated connection closes. Do not hold an open transaction while
        # the score engine reads other connections for every symbol.
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_advisory_lock(%s, %s)",
                (SCORE_OWNER_LOCK_NAMESPACE, int(user_id)),
            )
        conn.commit()
        # 1. Haal watchlist op
        if symbols is None:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol FROM watchlists WHERE user_id = %s
                    UNION SELECT symbol FROM setups WHERE user_id = %s
                    UNION SELECT symbol FROM user_indicator_configs
                          WHERE user_id = %s AND enabled = TRUE AND symbol IS NOT NULL
                            AND market_id IS NULL
                """, (user_id, user_id, user_id))
                watchlist = [str(row[0]).upper() for row in cur.fetchall() if row[0]]
            conn.commit()
        else:
            watchlist = list(dict.fromkeys(str(item).strip().upper() for item in symbols if item))

        # 2. Als er geen watchlist is, doen we een fallback naar BTC (of niks?)
        if not watchlist and symbols is None:
            logger.info(f"ℹ️ Geen watchlist voor user {user_id}. Gebruik BTC als fallback.")
            watchlist = ["BTC"]

        calculated = []
        for symbol in watchlist:
            logger.info(f"🔍 Scannen van asset {symbol} voor user {user_id}")
            
            macro = generate_scores_db("macro", user_id=user_id, symbol=symbol)
            technical = generate_scores_db("technical", user_id=user_id, symbol=symbol)
            market = generate_scores_db("market", user_id=user_id, symbol=symbol)

            # The score engine returns a display fallback of 10 when there
            # are no scored indicators. Persist NULL instead: an automated
            # Smart DCA decision must distinguish missing evidence from 10.
            macro_score = _confirmed_component_score(macro)
            technical_score = _confirmed_component_score(technical)
            market_score = _confirmed_component_score(market)

            calculated.append((symbol, macro, technical, market,
                               macro_score, technical_score, market_score))

        for symbol, macro, technical, market, macro_score, technical_score, market_score in calculated:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO daily_scores (
                        report_date, user_id, symbol,
                        macro_score, technical_score, market_score, setup_score,
                        macro_interpretation, technical_interpretation, market_interpretation,
                        macro_top_contributors, technical_top_contributors, market_top_contributors,
                        calculated_at, indicator_evidence
                    )
                    VALUES (
                        CURRENT_DATE, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        CURRENT_TIMESTAMP, %s::jsonb
                    )
                    ON CONFLICT (user_id, symbol, report_date) WHERE market_id IS NULL
                    DO UPDATE SET
                        macro_score = EXCLUDED.macro_score,
                        technical_score = EXCLUDED.technical_score,
                        market_score = EXCLUDED.market_score,
                        setup_score = EXCLUDED.setup_score,
                        macro_interpretation = EXCLUDED.macro_interpretation,
                        technical_interpretation = EXCLUDED.technical_interpretation,
                        market_interpretation = EXCLUDED.market_interpretation,
                        macro_top_contributors = EXCLUDED.macro_top_contributors,
                        technical_top_contributors = EXCLUDED.technical_top_contributors,
                        market_top_contributors = EXCLUDED.market_top_contributors,
                        calculated_at = EXCLUDED.calculated_at,
                        indicator_evidence = EXCLUDED.indicator_evidence;
                    """,
                    (
                        user_id, symbol,
                        macro_score, technical_score, market_score, None,
                        "Rule-based macro scan", "Rule-based technical scan", "Rule-based market scan",
                        _jsonb(list(macro.get("scores", {}).keys())),
                        _jsonb(list(technical.get("scores", {}).keys())),
                        _jsonb(list(market.get("scores", {}).keys())),
                        _jsonb({category: result.get("scores", {}) for category, result in (
                            ("macro", macro), ("technical", technical), ("market", market)
                        )}),
                    ),
                )
        
        conn.commit()
        saved_symbols = watchlist
        logger.info(f"💾 Daily scores voor watchlist opgeslagen (user_id={user_id})")

    except Exception:
        conn.rollback()
        logger.error(f"❌ Fout bij build_daily_scores_for_user ({user_id})", exc_info=True)
    finally:
        conn.close()

    # The feed is a downstream observer. A broker failure must never roll
    # back a correctly persisted score or create an item from a partial run.
    for symbol in saved_symbols:
        try:
            reconcile_coach_feed_score.delay(user_id, symbol)
        except Exception:
            logger.warning("FINN feed dispatch failed for %s", symbol, exc_info=True)


def build_daily_scores_for_market(user_id: int, market_id: int) -> dict:
    """Persist Score 2.0 for one exact pair without touching the base-asset row.

    Pair observations and indicator settings must already carry this market ID.
    No score is synthesized from the catalog's default pair or an FX conversion.
    """
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("exact_market_score_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_lock(%s, %s)",
                        (SCORE_OWNER_LOCK_NAMESPACE, int(user_id)))
        conn.commit()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT asset_symbol FROM trading_markets
                WHERE id=%s AND is_active=TRUE
            """, (market_id,))
            row = cur.fetchone()
        if not row:
            raise ValueError("exact_market_not_found")
        symbol = str(row[0]).upper()
        results = {
            category: generate_scores_db(category, user_id=user_id,
                                         symbol=symbol, market_id=market_id)
            for category in ("macro", "technical", "market")
        }
        scores = {category: _confirmed_component_score(results[category])
                  for category in results}
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO daily_scores (
                    report_date, user_id, symbol, market_id,
                    macro_score, technical_score, market_score, setup_score,
                    macro_interpretation, technical_interpretation, market_interpretation,
                    macro_top_contributors, technical_top_contributors, market_top_contributors,
                    calculated_at, indicator_evidence
                ) VALUES (
                    CURRENT_DATE, %s, %s, %s,
                    %s, %s, %s, NULL,
                    %s, %s, %s,
                    %s::jsonb, %s::jsonb, %s::jsonb,
                    CURRENT_TIMESTAMP, %s::jsonb
                )
                ON CONFLICT (user_id, market_id, report_date) WHERE market_id IS NOT NULL
                DO UPDATE SET
                    macro_score=EXCLUDED.macro_score,
                    technical_score=EXCLUDED.technical_score,
                    market_score=EXCLUDED.market_score,
                    setup_score=EXCLUDED.setup_score,
                    macro_interpretation=EXCLUDED.macro_interpretation,
                    technical_interpretation=EXCLUDED.technical_interpretation,
                    market_interpretation=EXCLUDED.market_interpretation,
                    macro_top_contributors=EXCLUDED.macro_top_contributors,
                    technical_top_contributors=EXCLUDED.technical_top_contributors,
                    market_top_contributors=EXCLUDED.market_top_contributors,
                    calculated_at=EXCLUDED.calculated_at,
                    indicator_evidence=EXCLUDED.indicator_evidence
            """, (
                user_id, symbol, market_id,
                scores["macro"], scores["technical"], scores["market"],
                "Rule-based macro scan", "Rule-based technical scan", "Rule-based market scan",
                _jsonb(list(results["macro"].get("scores", {}).keys())),
                _jsonb(list(results["technical"].get("scores", {}).keys())),
                _jsonb(list(results["market"].get("scores", {}).keys())),
                _jsonb({category: result.get("scores", {}) for category, result in results.items()}),
            ))
        conn.commit()
        return {"user_id": user_id, "symbol": symbol, "market_id": market_id,
                "scores": scores}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@shared_task(name="backend.celery_task.store_daily_scores_task.reconcile_coach_feed_score")
def reconcile_coach_feed_score(user_id: int, symbol: str):
    """Observe completed Score 2.0 output, never generate on a feed GET."""
    from backend.infrastructure.database import async_session_factory, run_celery_coroutine
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async def run():
        async with async_session_factory() as session:
            item_ids = await FinnCoachFeedService(session).reconcile_score_asset(
                user_id=user_id, symbol=symbol,
            )
            await session.commit()
            return item_ids

    try:
        for item_id in run_celery_coroutine(run()):
            generate_coach_feed_copy.delay(user_id, item_id)
    except Exception:
        logger.warning("FINN feed reconciliation failed for %s", symbol, exc_info=True)


@shared_task(name="backend.celery_task.store_daily_scores_task.generate_coach_feed_copy")
def generate_coach_feed_copy(user_id: int, item_id: str):
    """One bounded Luna/Responses attempt with a stored factual fallback."""
    from backend.infrastructure.database import async_session_factory, run_celery_coroutine
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async def run():
        async with async_session_factory() as session:
            result = await FinnCoachFeedService(session).generate_copy(
                user_id=user_id, item_id=item_id,
            )
            await session.commit()
            return result

    try:
        return run_celery_coroutine(run())
    except Exception:
        logger.warning("FINN feed copy failed", exc_info=True)
        return False


@shared_task(name="backend.celery_task.store_daily_scores_task.publish_coach_bot_decision")
def publish_coach_bot_decision(user_id: int, decision_id: int):
    """Only a persisted owner-owned Paper decision can enter the feed."""
    from sqlalchemy import text
    from backend.infrastructure.database import async_session_factory, run_celery_coroutine
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    async def run():
        async with async_session_factory() as session:
            result = await session.execute(text("""
                SELECT d.id, d.bot_id, d.symbol, d.action, d.status, d.decision_ts,
                       b.name AS bot_name, b.is_live
                FROM bot_decisions d JOIN bot_configs b
                  ON b.id=d.bot_id AND b.user_id=d.user_id
                WHERE d.id=:decision_id AND d.user_id=:user_id
            """), {"decision_id": decision_id, "user_id": user_id})
            row = result.mappings().first()
            if not row or row["is_live"] or str(row["action"] or "").lower() in {"hold", "houd_vast", "none"}:
                return None
            item_id = await FinnCoachFeedService(session).publish(
                user_id=user_id, event_key=f"bot-decision:{decision_id}",
                event_type="bot_decision", subject_type="bot",
                subject_id=str(row["bot_id"]), subject=row["bot_name"],
                symbol=row["symbol"], priority=2,
                source_observed_at=row["decision_ts"],
                evidence={"status": row["status"], "action": row["action"],
                          "decision_id": row["id"], "bot_id": row["bot_id"],
                          "source_observed_at": row["decision_ts"]},
                revision=f"{row['action']}:{row['status']}",
            )
            await session.commit()
            return item_id

    try:
        item_id = run_celery_coroutine(run())
        if item_id:
            generate_coach_feed_copy.delay(user_id, item_id)
    except Exception:
        logger.warning("FINN Paper decision feed dispatch failed", exc_info=True)


@shared_task(name="backend.celery_task.store_daily_scores_task.retry_coach_feed_copy")
def retry_coach_feed_copy():
    """Recover bounded text generation without opening the UI or replaying events."""
    from backend.utils.db import get_db_connection

    conn = get_db_connection()
    if conn is None:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE finn_coach_feed_items f SET status='resolved',
                    updated_at=NOW()
                WHERE f.status IN ('unread','read') AND (
                  (f.expires_at IS NOT NULL AND f.expires_at <= NOW())
                  OR (f.event_type='proposal_pending' AND NOT EXISTS (
                      SELECT 1 FROM finn_v2_proposals p
                      WHERE p.id=f.subject_id AND p.user_id=f.user_id
                        AND p.status IN ('draft','pending_confirmation')
                        AND p.expires_at > NOW()))
                )
            """)
            cur.execute("""
                SELECT user_id, id FROM finn_coach_feed_items
                WHERE copy_source='fact_fallback' AND copy_attempts < 3
                  AND status IN ('unread','read')
                  AND (expires_at IS NULL OR expires_at > NOW())
                  AND (copy_last_attempt_at IS NULL
                       OR copy_last_attempt_at < NOW() - INTERVAL '10 minutes')
                ORDER BY CASE WHEN event_type='proposal_pending' THEN 0 ELSE 1 END,
                         created_at ASC LIMIT 6
            """)
            items = cur.fetchall()
        conn.commit()
        for user_id, item_id in items:
            generate_coach_feed_copy.delay(user_id, str(item_id))
        return len(items)
    finally:
        conn.close()


@shared_task(name="backend.celery_task.store_daily_scores_task.recover_coach_feed_events")
def recover_coach_feed_events():
    """Recover new persisted Paper events; the score sweep rechecks plans."""
    conn = get_db_connection()
    if conn is None:
        return 0
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT d.user_id, d.id FROM bot_decisions d
                JOIN bot_configs b ON b.id=d.bot_id AND b.user_id=d.user_id
                CROSS JOIN finn_coach_feed_runtime r
                WHERE r.singleton=TRUE AND d.id > r.initial_decision_id
                  AND COALESCE(b.is_live, FALSE)=FALSE
                  AND LOWER(COALESCE(d.action, '')) NOT IN ('hold', 'houd_vast', 'none', '')
                  AND NOT EXISTS (
                    SELECT 1 FROM finn_coach_feed_items f
                    WHERE f.user_id=d.user_id AND f.event_key='bot-decision:' || d.id::TEXT)
                ORDER BY d.id LIMIT 12
            """)
            decisions = cur.fetchall()
        conn.commit()
    finally:
        conn.close()
    dispatched = 0
    for user_id, decision_id in decisions:
        try:
            publish_coach_bot_decision.delay(user_id, decision_id)
            dispatched += 1
        except Exception:
            logger.warning("FINN feed Paper recovery dispatch failed", exc_info=True)
    return dispatched


# =========================================================
# 2️⃣ CELERY TASK: RULE-BASED DAILY SCORES (ALLE USERS)
# =========================================================
@shared_task(
    name="backend.celery_task.store_daily_scores_task.store_daily_scores_task"
)
def store_daily_scores_task(user_id: int, symbol: str | None = None):
    """
    Bouwt daily scores voor precies één user.

    Deze wrapper wordt gebruikt door de onboarding-pipeline zodat
    de eerste persoonlijke report- en briefingketen echt kan starten.
    """
    if user_id is None:
        raise ValueError("❌ user_id is verplicht voor store_daily_scores_task")

    build_daily_scores_for_user(user_id, [symbol] if symbol else None)


@shared_task(
    name="backend.celery_task.store_daily_scores_task.run_rule_based_daily_scores"
)
def run_rule_based_daily_scores():
    """
    Draait rule-based scoring voor alle users.

    De setupmatch wordt bij het lezen uit deze drie componentscores berekend.
    """

    lease_client = _try_acquire_rule_based_scores_lease()
    if lease_client is None:
        logger.warning("⏭️ RULE-BASED daily_scores overgeslagen: vorige run is nog actief")
        return {"ok": True, "skipped": True, "reason": "lease_already_active"}

    logger.info("🚀 Start RULE-BASED daily_scores (alle users)")

    try:
        conn = get_db_connection()
        if not conn:
            logger.error("❌ Geen DB-verbinding")
            return

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id FROM users
                    WHERE COALESCE(ai_preferences #>> '{capacity_fixture,kind}', '') <> 'read_only_load_v1';
                """)
                users = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

        for user_id in users:
            build_daily_scores_for_user(user_id)

        logger.info("✅ RULE-BASED daily_scores klaar")
    finally:
        _release_rule_based_scores_lease(lease_client)
