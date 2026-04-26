import logging
import json
from datetime import date
from typing import Optional, Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json, ask_gpt_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def run_macro_agent(user_id: int):
    """
    Genereert Macro AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Deze agent analyseert de markt voor een specifieke user.
    """
    logger.info(f"🌍 [Macro-Agent] Start Analysis for user_id={user_id}")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # 1️⃣ HAAL MACRO DATA OP VOOR DEZE USER
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (name)
                    name,
                    value,
                    timestamp
                FROM macro_data
                WHERE user_id = %s
                ORDER BY name, timestamp DESC;
            """, (user_id,))
            rows = cur.fetchall()

        if not rows:
            logger.warning(f"⚠️ [Macro-Agent] Geen macro data beschikbaar voor user_id={user_id}.")
            return

        macro_data = [
            {
                "indicator": name,
                "value": float(value) if value is not None else None,
                "timestamp": ts.isoformat() if ts else None,
            }
            for name, value, ts in rows
        ]

        # 2️⃣ BEREID PROMPT VOOR
        system_prompt = build_system_prompt(
            agent="macro",
            task="""
Je bent een senior macro-analist. Analyseer de onderstaande marktgegevens voor Bitcoin.
Focus op de feitelijke data en trends. Breng complexe macro-interacties terug naar een helder inzicht.

GEEF JE ANTWOORD IN JSON FORMAT MET DE VOLGENDE VELDEN:
- score: (0-100)
- trend: (bullish, bearish, neutraal)
- bias: (afwachtend, agressief, defensief)
- risk: (laag, gemiddeld, hoog)
- summary: (korte samenvatting)
- top_signals: (lijst van strings met belangrijkste signalen)

WAARSCHUWING: Geef GEEN financieel advies.
""")

        payload = {
            "market_snapshot": macro_data,
            "analysis_date": date.today().isoformat()
        }

        # 3️⃣ AI CALL
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # 4️⃣ OPSLAAN IN AI_CATEGORY_INSIGHTS (waar dashboard naar kijkt)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights
                    (user_id, category, avg_score, trend, bias, risk, summary, top_signals, date)
                VALUES (%s, 'macro', %s, %s, %s, %s, %s, %s, CURRENT_DATE)
                ON CONFLICT (user_id, category, date)
                DO UPDATE SET
                    avg_score = EXCLUDED.avg_score,
                    trend = EXCLUDED.trend,
                    bias = EXCLUDED.bias,
                    risk = EXCLUDED.risk,
                    summary = EXCLUDED.summary,
                    top_signals = EXCLUDED.top_signals,
                    created_at = NOW();
            """, (
                user_id,
                raw_ai_response.get("score", 50),
                raw_ai_response.get("trend", "neutraal"),
                raw_ai_response.get("bias", "afwachtend"),
                raw_ai_response.get("risk", "gemiddeld"),
                raw_ai_response.get("summary", ""),
                json.dumps(raw_ai_response.get("top_signals", [])),
            ))

        conn.commit()
        logger.info(f"✅ [Macro-Agent] Analysis voltooid voor user_id={user_id}")

    except Exception:
        if conn: conn.rollback()
        logger.error(f"❌ [Macro-Agent] Fout tijdens run voor user_id={user_id}", exc_info=True)
    finally:
        if conn: conn.close()
