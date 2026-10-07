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

    try:
        # 1. Haal watchlist op
        if symbols is None:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT symbol FROM watchlists WHERE user_id = %s
                    UNION SELECT symbol FROM setups WHERE user_id = %s
                    UNION SELECT symbol FROM user_indicator_configs
                          WHERE user_id = %s AND enabled = TRUE AND symbol IS NOT NULL
                """, (user_id, user_id, user_id))
                watchlist = [str(row[0]).upper() for row in cur.fetchall() if row[0]]
        else:
            watchlist = list(dict.fromkeys(str(item).strip().upper() for item in symbols if item))

        # 2. Als er geen watchlist is, doen we een fallback naar BTC (of niks?)
        if not watchlist and symbols is None:
            logger.info(f"ℹ️ Geen watchlist voor user {user_id}. Gebruik BTC als fallback.")
            watchlist = ["BTC"]

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
                    ON CONFLICT (user_id, symbol, report_date)
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
        logger.info(f"💾 Daily scores voor watchlist opgeslagen (user_id={user_id})")

    except Exception:
        conn.rollback()
        logger.error(f"❌ Fout bij build_daily_scores_for_user ({user_id})", exc_info=True)
    finally:
        conn.close()


# =========================================================
# 2️⃣ CELERY TASK: RULE-BASED DAILY SCORES (ALLE USERS)
# =========================================================
@shared_task(
    name="backend.celery_task.store_daily_scores_task.store_daily_scores_task"
)
def store_daily_scores_task(user_id: int):
    """
    Bouwt daily scores voor precies één user.

    Deze wrapper wordt gebruikt door de onboarding-pipeline zodat
    de eerste persoonlijke report- en briefingketen echt kan starten.
    """
    if user_id is None:
        raise ValueError("❌ user_id is verplicht voor store_daily_scores_task")

    build_daily_scores_for_user(user_id)


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
                cur.execute("SELECT id FROM users;")
                users = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

        for user_id in users:
            build_daily_scores_for_user(user_id)

        logger.info("✅ RULE-BASED daily_scores klaar")
    finally:
        _release_rule_based_scores_lease(lease_client)
