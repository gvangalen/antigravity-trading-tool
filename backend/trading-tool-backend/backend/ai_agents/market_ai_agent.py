import logging
import json
from datetime import date
from typing import Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json_json, ask_gpt_text
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def run_market_agent():
    """
    Genereert Market AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Analyseert Sentiment, Dominantie en Volume voor het hele platform.
    """
    logger.info("🌍 [Market-Agent] Start Global AI Analysis")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        # 1️⃣ HAAL GLOBALE MARKET DATA OP
        with conn.cursor() as cur:
            # A. Market Indicators (BTC Dom, Fear & Greed, etc.)
            cur.execute("""
                SELECT DISTINCT ON (name)
                    name, value, timestamp
                FROM global_market_indicators
                ORDER BY name, timestamp DESC;
            """)
            indicator_rows = cur.fetchall()

            # B. Raw Market Data (Price, Volume, Change)
            cur.execute("""
                SELECT symbol, price, volume, change_24h, timestamp
                FROM market_data
                WHERE symbol IN ('BTC', 'ETH')
                ORDER BY timestamp DESC
                LIMIT 10;
            """)
            market_rows = cur.fetchall()

        if not indicator_rows and not market_rows:
            logger.warning("⚠️ [Market-Agent] Geen data beschikbaar voor analyse.")
            return

        market_snapshot = {
            "indicators": [
                {"name": name, "value": float(value) if value is not None else None}
                for name, value, ts in indicator_rows
            ],
            "prices": [
                {
                    "symbol": sym, 
                    "price": float(p), 
                    "volume": float(v), 
                    "change_24h": float(c)
                }
                for sym, p, v, c, ts in market_rows
            ]
        }

        # 2️⃣ BEREID PROMPT VOOR
        system_prompt = build_system_prompt(
            agent="market",
            task="""
Je bent een specialist in crypto-marktsentiment en on-chain data.
Analyseer de huidige marktdynamiek op basis van prijzen, volume en sentiment-indicatoren.
Geef een heldere conclusie over het huidige momentum.

WAARSCHUWING: Geef GEEN financieel advies.
""")

        # 3️⃣ AI CALL
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(market_snapshot, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # 4️⃣ OPSLAAN IN GLOBAL MARKET INSIGHTS
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO global_market_insights
                    (category, avg_score, trend, bias, risk, summary, top_signals)
                VALUES ('market', %s, %s, %s, %s, %s, %s)
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
        logger.info("✅ [Market-Agent] Global Analysis voltooid")

    except Exception:
        conn.rollback()
        logger.error("❌ [Market-Agent] Fout tijdens global run", exc_info=True)
    finally:
        conn.close()
