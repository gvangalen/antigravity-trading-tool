import logging
import json
import hashlib
from decimal import Decimal
from typing import Any, Callable, Dict, Optional, Tuple

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json
from backend.ai_core.system_prompt_builder import build_system_prompt
from backend.ai_core.agent_context import build_agent_context  # ✅ gedeelde context
from backend.services.ai_usage_observability_service import ai_usage_context, log_background_ai_skip

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _setup_input_hash(asset: str, best: Dict[str, Any]) -> str:
    components = best.get("components") or {}
    payload = {
        "asset": str(asset or "BTC").upper(),
        "setup_id": best.get("setup_id"),
        "name": best.get("name"),
        "setup_type": best.get("setup_type"),
        "dca_config": best.get("dca_config") or {},
        # Five-point buckets prevent insignificant score noise from invoking AI.
        "score_bucket": round(float(best.get("score") or 0) / 5) * 5,
        "component_buckets": {
            key: round(float(value or 0) / 5) * 5
            for key, value in sorted(components.items())
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _stored_setup_explanation(conn, *, user_id: int, asset: str, setup_id: int, input_hash: str) -> Optional[str]:
    marker = f"input_hash:{input_hash}"
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT date
            FROM ai_category_insights
            WHERE user_id = %s
              AND category = 'setup'
              AND symbol = %s
              AND top_signals @> %s::jsonb
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            """,
            (user_id, asset, json.dumps([marker])),
        )
        insight_row = cur.fetchone()
        if not insight_row:
            return None
        cur.execute(
            """
            SELECT explanation
            FROM daily_setup_scores
            WHERE user_id = %s AND setup_id = %s AND report_date = %s
            LIMIT 1
            """,
            (user_id, setup_id, insight_row[0]),
        )
        row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _reuse_or_generate_explanation(
    existing: Optional[str],
    generator: Callable[[], str],
) -> Tuple[str, bool]:
    """Return persisted text without evaluating the AI generator when possible."""
    if existing is not None:
        return existing, True
    return generator(), False


# ======================================================
# 🔢 HELPERS
# ======================================================

def to_float(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except Exception:
        return None


def score_overlap(value, min_v, max_v) -> int:
    """
    Overlap-score (0–100) met soft decay: -2 punten per 1 punt afwijking.
    """
    value = to_float(value)
    min_v = to_float(min_v)
    max_v = to_float(max_v)

    if value is None:
        return 0

    if min_v is None and max_v is None:
        return 100

    # Soft decay penalty logica
    penalty = 0
    if min_v is not None and value < min_v:
        penalty = (min_v - value) * 2
    elif max_v is not None and value > max_v:
        penalty = (value - max_v) * 2

    if penalty > 0:
        return max(0, round(100 - penalty))

    # Binnen de range
    if min_v is None or max_v is None:
        return 100

    mid = (min_v + max_v) / 2
    max_dist = (max_v - min_v) / 2
    if max_dist <= 0:
        return 100

    return round(100 - (abs(value - mid) / max_dist * 100))


# ======================================================
# 🤖 SETUP AI AGENT — MET GEHEUGEN
# ======================================================
def run_setup_agent(*, user_id: int, asset: str = "BTC"):

    if not user_id:
        raise ValueError("❌ Setup agent vereist user_id")

    logger.info(f"🤖 [Setup-Agent] Start (user_id={user_id}, asset={asset})")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # ==================================================
        # 1️⃣ DAGELIJKSE MARKTCONTEXT
        # ==================================================
        with conn.cursor() as cur:
            cur.execute("""
                SELECT macro_score, technical_score, market_score
                FROM daily_scores
                WHERE report_date = CURRENT_DATE
                  AND user_id = %s
                LIMIT 1
            """, (user_id,))
            row = cur.fetchone()

        if not row:
            logger.warning("⚠️ Geen daily_scores gevonden")
            return

        macro, technical, market = map(to_float, row)

        # ==================================================
        # 2️⃣ SETUPS OPHALEN
        # ==================================================
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    name,
                    setup_type,
                    dca_frequency,
                    dca_day,
                    dca_month_day,
                    min_macro_score,
                    max_macro_score,
                    min_technical_score,
                    max_technical_score,
                    min_market_score,
                    max_market_score
                FROM setups
                WHERE user_id = %s
                  AND symbol = %s
                ORDER BY created_at DESC
            """, (user_id, asset))
            setups = cur.fetchall()

        if not setups:
            logger.info("ℹ️ Geen setups gevonden")
            return

        # ==================================================
        # 3️⃣ RESET BEST-FLAG
        # ==================================================
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE daily_setup_scores
                SET is_best = FALSE
                WHERE user_id = %s
                  AND report_date = CURRENT_DATE
            """, (user_id,))

        evaluations = []

        # ==================================================
        # 4️⃣ LOKALE OVERLAP BEREKENING (SNEL)
        # ==================================================
        for row_setup in setups:
            (
                setup_id,
                name,
                setup_type,
                dca_frequency,
                dca_day,
                dca_month_day,
                min_macro,
                max_macro,
                min_tech,
                max_tech,
                min_market,
                max_market
            ) = row_setup

            m  = score_overlap(macro, min_macro, max_macro)
            t  = score_overlap(technical, min_tech, max_tech)
            mk = score_overlap(market, min_market, max_market)

            # Slimme weging: negeer niet-geconfigureerde domeinen in het gemiddelde
            active_components = 0
            total_score = 0
            
            if min_macro is not None or max_macro is not None:
                active_components += 1
                total_score += m
            if min_tech is not None or max_tech is not None:
                active_components += 1
                total_score += t
            if min_market is not None or max_market is not None:
                active_components += 1
                total_score += mk
                
            if active_components == 0:
                raw_score = round((m + t + mk) / 3) # Fallback
            else:
                raw_score = round(total_score / active_components)

            score = max(25, raw_score)

            evaluations.append({
                "setup_id": setup_id,
                "name": name,
                "setup_type": setup_type,
                "dca_config": {
                    "frequency": dca_frequency,
                    "day": dca_day,
                    "month_day": dca_month_day
                },
                "score": score,
                "components": {"m": m, "t": t, "mk": mk}
            })

        # Sorteer om de winnaar te bepalen
        ranked = sorted(evaluations, key=lambda x: x["score"], reverse=True)
        best = ranked[0]
        asset = str(asset or "BTC").upper()
        input_hash = _setup_input_hash(asset, best)
        explanation = _stored_setup_explanation(
            conn,
            user_id=user_id,
            asset=asset,
            setup_id=best["setup_id"],
            input_hash=input_hash,
        )

        # ==================================================
        # 5️⃣ AI TASK (EENMALIG VOOR DE BESTE SETUP)
        # ==================================================
        SETUP_TASK = """
Je bent een trading decision agent.

Gebruik:
- macro / technical / market scores
- overlap-scores per setup
- setup_type (belangrijk!)
- context t.o.v. gisteren

Leg uit:
- of deze setup sterker / zwakker / gelijk is
- of dit rotatie is of continuatie
- waarom deze setup NU logisch is

GEEN:
- voorspellingen
- educatie

Output: 2–3 zinnen.
"""
        system_prompt = build_system_prompt(agent="setup", task=SETUP_TASK)

        def generate_explanation() -> str:
            with ai_usage_context(
                user_id=user_id,
                symbol=asset,
                purpose="setup_analysis",
                request_source="background_job",
                run_kind="scheduled",
                entry_point="setup_ai_agent:run_setup_agent",
                caller_tag="setup_ai_agent:run_setup_agent",
            ):
                return ask_gpt_text(
                    prompt=json.dumps({
                        "setup": best["name"],
                        "setup_type": best["setup_type"],
                        "dca_config": best["dca_config"],
                        "macro_score": macro,
                        "technical_score": technical,
                        "market_score": market,
                        "component_overlap": best["components"]
                    }, ensure_ascii=False, indent=2),
                    system_role=system_prompt
                )

        explanation, reused_explanation = _reuse_or_generate_explanation(
            explanation,
            generate_explanation,
        )
        if reused_explanation:
            logger.info("♻️ Setup AI overgeslagen: input onveranderd | user=%s asset=%s", user_id, asset)
            log_background_ai_skip(
                user_id=user_id,
                symbol=asset,
                purpose="setup_analysis",
                entry_point="setup_ai_agent:run_setup_agent",
            )

        # ==================================================
        # 6️⃣ OPSLAAN VOOR ALLE SETUPS
        # ==================================================
        for eval_obj in ranked:
            is_best_setup = (eval_obj["setup_id"] == best["setup_id"])
            current_explanation = explanation if is_best_setup else "Berekend via mechanische overlap."
            
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO daily_setup_scores
                        (setup_id, user_id, report_date, score, is_active, explanation)
                    VALUES (%s, %s, CURRENT_DATE, %s, TRUE, %s)
                    ON CONFLICT (setup_id, user_id, report_date)
                    DO UPDATE SET
                        score = EXCLUDED.score,
                        is_active = TRUE,
                        explanation = EXCLUDED.explanation,
                        created_at = NOW()
                """, (eval_obj["setup_id"], user_id, eval_obj["score"], current_explanation))


        # ==================================================
        # 7️⃣ BESTE SETUP MARKEREN & SCORE OPSLAAN
        # ==================================================
        agent_context = build_agent_context(
            user_id=user_id,
            category="setup",
            current_score=best["score"],
            current_items=ranked[:3],
            lookback_days=1
        )

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE daily_setup_scores
                SET is_best = TRUE
                WHERE setup_id = %s
                  AND user_id = %s
                  AND report_date = CURRENT_DATE
            """, (best["setup_id"], user_id))

            cur.execute("""
                UPDATE daily_scores
                SET setup_score = %s
                WHERE user_id = %s
                  AND report_date = CURRENT_DATE
                  AND symbol = %s
            """, (best["score"], user_id, asset))


        # ==================================================
        # 8️⃣ INSIGHT (VOOR DASHBOARD)
        # ==================================================
        summary = f"Beste {asset}-setup: {best['name']} ({best['setup_type']})"

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights
                    (category, user_id, symbol, avg_score, trend, bias, risk, summary, top_signals)
                VALUES ('setup', %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (user_id, category, symbol, date)
                DO UPDATE SET
                    avg_score = EXCLUDED.avg_score,
                    summary = EXCLUDED.summary,
                    top_signals = EXCLUDED.top_signals,
                    created_at = NOW()
            """, (
                user_id,
                asset,
                best["score"],
                "Actief" if best["score"] >= 60 else "Neutraal",
                "Kansrijk" if best["score"] >= 60 else "Afwachten",
                "Gemiddeld",
                summary,
                json.dumps([
                    f"{best['name']} beste match",
                    f"Type: {best['setup_type']}",
                    f"input_hash:{input_hash}",
                ])
            ))

        conn.commit()
        logger.info("✅ Setup agent klaar")

    except Exception:
        if conn: conn.rollback()
        logger.error("❌ Setup agent crash", exc_info=True)

    finally:
        if conn: conn.close()

# ======================================================
# 🧠 UITLEG PER SETUP (API)
# ======================================================
def generate_setup_explanation(setup_id: int, user_id: int) -> str:

    conn = get_db_connection()
    if not conn:
        return ""

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    name,
                    symbol,
                    setup_type,
                    dca_frequency,
                    dca_day,
                    dca_month_day,
                    description,
                    action
                FROM setups
                WHERE id = %s AND user_id = %s
            """, (setup_id, user_id))
            row = cur.fetchone()

        if not row:
            return ""

        (
            name,
            symbol,
            setup_type,
            dca_frequency,
            dca_day,
            dca_month_day,
            description,
            action
        ) = row

        TASK = """
Leg kort uit waarom deze setup logisch is.
Gebruik setup_type en gedrag.
Geen educatie of voorspellingen.
"""

        system_prompt = build_system_prompt(agent="setup", task=TASK)

        with ai_usage_context(
            user_id=user_id,
            symbol=symbol,
            purpose="setup_explanation",
            entry_point="setup_ai_agent:generate_setup_explanation",
            caller_tag="setup_ai_agent:generate_setup_explanation",
        ):
            return ask_gpt_text(
                prompt=json.dumps({
                    "setup": name,
                    "symbol": symbol,
                    "setup_type": setup_type,
                    "dca_config": {
                        "frequency": dca_frequency,
                        "day": dca_day,
                        "month_day": dca_month_day
                    },
                    "description": description,
                    "action": action
                }, ensure_ascii=False, indent=2),
                system_role=system_prompt
            )

    except Exception:
        logger.error("❌ generate_setup_explanation fout", exc_info=True)
        return ""

    finally:
        if conn: conn.close()
