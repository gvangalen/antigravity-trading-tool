import logging
import json
from datetime import date
from typing import Optional, Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json, ask_gpt_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def run_macro_agent():
    """
    Genereert Macro AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Deze agent analyseert de markt voor het hele platform (1x per dag).
    """
    logger.info("🌍 [Macro-Agent] Start Global AI Analysis")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # 1️⃣ HAAL GLOBALE MACRO DATA OP (Objectieve Bron)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT ON (name)
                    name,
                    value,
                    timestamp
                FROM global_macro_data
                ORDER BY name, timestamp DESC;
            """)
            rows = cur.fetchall()

        if not rows:
            logger.warning("⚠️ [Macro-Agent] Geen globale macro data beschikbaar voor analyse.")
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
Dit is een platform-brede analyse (Global Intelligence Layer).
Focus op de feitelijke data en trends. Breng complexe macro-interacties terug naar een helder inzicht.

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

        # 4️⃣ OPSLAAN IN GLOBAL MARKET INSIGHTS
        # We verwachten velden: trend, bias, risk, summary, top_signals
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO global_market_insights
                    (category, avg_score, trend, bias, risk, summary, top_signals)
                VALUES ('macro', %s, %s, %s, %s, %s, %s)
                ON CONFLICT (category, date)
                DO UPDATE SET
                    trend = EXCLUDED.trend,
                    bias = EXCLUDED.bias,
                    risk = EXCLUDED.risk,
                    summary = EXCLUDED.summary,
                    top_signals = EXCLUDED.top_signals,
                    created_at = NOW();
            """, (
                50, # We doen geen gemiddelde score meer in de AI laag (wordt berekend door User Scoring)
                raw_ai_response.get("trend", "neutraal"),
                raw_ai_response.get("bias", "afwachtend"),
                raw_ai_response.get("risk", "gemiddeld"),
                raw_ai_response.get("summary", ""),
                json.dumps(raw_ai_response.get("top_signals", [])),
            ))

        conn.commit()
        logger.info("✅ [Macro-Agent] Global Analysis voltooid")

    except Exception:
        conn.rollback()
        logger.error("❌ [Macro-Agent] Fout tijdens global run", exc_info=True)
    finally:
        conn.close()
