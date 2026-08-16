import logging
import json
import os
from celery import shared_task

from backend.utils.db import get_db_connection
from backend.utils.scoring_utils import generate_scores_db
from backend.ai_agents.score_ai_agent import generate_master_score

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

RULE_BASED_SCORES_LEASE_KEY = "task-lease:run_rule_based_daily_scores"
RULE_BASED_SCORES_LEASE_SECONDS = 30 * 60


def _jsonb(value):
    """Zorgt dat we altijd geldige JSON naar jsonb casten."""
    return json.dumps(value or [], ensure_ascii=False)


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
# 🔎 Setup-score ophalen UIT SETUP AGENT
# =========================================================
def fetch_setup_score_from_setup_agent(conn, user_id: int):
    """
    Setup-score is BRON:
    ai_category_insights WHERE category='setup'
    (gevuld door run_setup_agent)
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT avg_score
            FROM ai_category_insights
            WHERE user_id = %s
              AND category = 'setup'
              AND date = CURRENT_DATE
            LIMIT 1;
            """,
            (user_id,),
        )
        row = cur.fetchone()

    if not row or row[0] is None:
        logger.warning(f"⚠️ Geen setup-score gevonden (user_id={user_id})")
        return None

    return float(row[0])


# =========================================================
# 1️⃣ BUILD DAILY SCORES (RULE-BASED) — PER USER
# =========================================================
def build_daily_scores_for_user(user_id: int):
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
        with conn.cursor() as cur:
            cur.execute("SELECT symbol FROM watchlists WHERE user_id = %s", (user_id,))
            watchlist = [r[0] for r in cur.fetchall()]

        # 2. Als er geen watchlist is, doen we een fallback naar BTC (of niks?)
        if not watchlist:
            logger.info(f"ℹ️ Geen watchlist voor user {user_id}. Gebruik BTC als fallback.")
            watchlist = ["BTC"]

        for symbol in watchlist:
            logger.info(f"🔍 Scannen van asset {symbol} voor user {user_id}")
            
            macro = generate_scores_db("macro", user_id=user_id) # Macro is vaak global maar kan symbol-aware zijn
            technical = generate_scores_db("technical", user_id=user_id, symbol=symbol)
            market = generate_scores_db("market", user_id=user_id, symbol=symbol)

            macro_score = macro.get("total_score", 50)
            technical_score = technical.get("total_score", 50)
            market_score = market.get("total_score", 50)

            # 🔥 Setup-score UIT setup agent (per asset?)
            # Voorlopig is setup agent nog globaal/per user. 
            # TODO: Setup agent symbol-aware maken indien nodig.
            setup_score = fetch_setup_score_from_setup_agent(conn, user_id)

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO daily_scores (
                        report_date, user_id, symbol,
                        macro_score, technical_score, market_score, setup_score,
                        macro_interpretation, technical_interpretation, market_interpretation,
                        macro_top_contributors, technical_top_contributors, market_top_contributors
                    )
                    VALUES (
                        CURRENT_DATE, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb
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
                        market_top_contributors = EXCLUDED.market_top_contributors;
                    """,
                    (
                        user_id, symbol,
                        macro_score, technical_score, market_score, setup_score,
                        "Rule-based macro scan", "Rule-based technical scan", "Rule-based market scan",
                        _jsonb(list(macro.get("scores", {}).keys())),
                        _jsonb(list(technical.get("scores", {}).keys())),
                        _jsonb(list(market.get("scores", {}).keys())),
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

    ⚠️ BELANGRIJK:
    Deze task VERWACHT dat de setup agent
    AL GEDRAAID heeft voor vandaag.
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


# =========================================================
# 3️⃣ CELERY TASK: MASTER SCORE AI (ALLE USERS)
# =========================================================
@shared_task(
    name="backend.celery_task.store_daily_scores_task.run_master_score_ai"
)
def run_master_score_ai():
    """
    Draait de MASTER orchestrator AI.

    Leest:
      - daily_scores
      - ai_category_insights (incl. setup)

    Schrijft:
      - ai_category_insights (category='master')
    """

    logger.info("🧠 Start MASTER Score AI (alle users)")

    try:
        generate_master_score()
        logger.info("✅ MASTER Score AI afgerond")
    except Exception:
        logger.error("❌ Fout tijdens MASTER Score AI", exc_info=True)
        raise
