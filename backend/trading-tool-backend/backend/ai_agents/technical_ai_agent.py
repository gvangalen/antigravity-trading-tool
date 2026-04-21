import logging
import json
from datetime import date
from typing import Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def run_technical_agent():
    """
    Genereert Technical AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Analyseert RSI, MACD, Moving Averages etc. voor het hele platform.
    """
    logger.info("🌍 [Technical-Agent] Start Global AI Analysis")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # 1️⃣ HAAL GLOBALE TECHNICAL DATA OP
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (indicator)
                    indicator, value, timestamp
                FROM global_technical_indicators
                ORDER BY indicator, timestamp DESC;
            """)
            rows = cur.fetchall()

        if not rows:
            logger.warning("⚠️ [Technical-Agent] Geen technische data beschikbaar voor analyse.")
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

WAARSCHUWING: Geef GEEN financieel advies.
""")

        # 3️⃣ AI CALL
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(tech_snapshot, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # 4️⃣ OPSLAAN IN GLOBAL MARKET INSIGHTS
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO global_market_insights
                    (category, avg_score, trend, bias, risk, summary, top_signals)
                VALUES ('technical', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (category, date)
                DO UPDATE SET
                    trend = EXCLUDED.trend,
                    bias = EXCLUDED.bias,
                    risk = EXCLUDED.risk,
                    summary = EXCLUDED.summary,
                    top_signals = EXCLUDED.top_signals,
                    created_at = NOW();
            """, (
                50,
                raw_ai_response.get("trend", "neutraal"),
                raw_ai_response.get("bias", "afwachtend"),
                raw_ai_response.get("risk", "gemiddeld"),
                raw_ai_response.get("summary", ""),
                json.dumps(raw_ai_response.get("top_signals", [])),
            ))

        conn.commit()
        logger.info("✅ [Technical-Agent] Global Analysis voltooid")

    except Exception:
        conn.rollback()
        logger.error("❌ [Technical-Agent] Fout tijdens global run", exc_info=True)
    finally:
        conn.close()
