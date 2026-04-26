import logging
import json
from datetime import date
from typing import Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def run_technical_agent(user_id: int):
    """
    Genereert Technical AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Analyseert RSI, MACD, Moving Averages etc. voor een specifieke user.
    """
    logger.info(f"🌍 [Technical-Agent] Start Analysis for user_id={user_id}")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # 1️⃣ HAAL TECHNICAL DATA OP VOOR DEZE USER
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (indicator)
                    indicator, value, timestamp
                FROM technical_indicators
                WHERE user_id = %s
                ORDER BY indicator, timestamp DESC;
            """, (user_id,))
            rows = cur.fetchall()

        if not rows:
            logger.warning(f"⚠️ [Technical-Agent] Geen technische data beschikbaar voor user_id={user_id}.")
            return

        tech_snapshot = [
            {"indicator": ind, "value": float(v) if v is not None else None}
            for ind, v, ts in rows
        ]

        # 2️⃣ BEREID PROMPT VOOR
        system_prompt = build_system_prompt(
            agent="technical",
            task="""
Je bent een technisch analist gespecialiseerd in prijsactie, indicatoren en marktstructuur.
Analyseer de technische staat van de markt (focus op BTC).
Vat samen of we in een overbought/oversold conditie zitten en wat de meest waarschijnlijke richting is op korte termijn.

GEEF JE ANTWOORD IN JSON FORMAT MET DE VOLGENDE VELDEN:
- score: (0-100)
- trend: (bullish, bearish, neutraal)
- bias: (afwachtend, agressief, defensief)
- risk: (laag, gemiddeld, hoog)
- summary: (korte samenvatting)
- top_signals: (lijst van strings met belangrijkste signalen)

WAARSCHUWING: Geef GEEN financieel advies.
""")

        # 3️⃣ AI CALL
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(tech_snapshot, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # 4️⃣ OPSLAAN IN AI_CATEGORY_INSIGHTS (waar dashboard naar kijkt)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights
                    (user_id, category, avg_score, trend, bias, risk, summary, top_signals, date)
                VALUES (%s, 'technical', %s, %s, %s, %s, %s, %s, CURRENT_DATE)
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
        logger.info(f"✅ [Technical-Agent] Analysis voltooid voor user_id={user_id}")

    except Exception:
        if conn: conn.rollback()
        logger.error(f"❌ [Technical-Agent] Fout tijdens run voor user_id={user_id}", exc_info=True)
    finally:
        if conn: conn.close()
