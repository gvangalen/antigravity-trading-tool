import logging
import json
from datetime import date, timedelta
from typing import Dict, Any, List

from backend.utils.db import get_db_connection
from backend.utils.openai_client import ask_gpt_text, ask_gpt_json
from backend.ai_core.system_prompt_builder import build_system_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def _clamp_score(v: Any, *, default: float = 50.0, lo: float = 0.0, hi: float = 100.0) -> float:
    try:
        x = float(v)
        if x != x:  # NaN
            x = default
    except Exception:
        x = default

    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return float(x)

def run_market_agent(user_id: int):
    """
    Genereert Market AI insights op basis van de GLOBALE OBJECTIEVE bron.
    Analyseert Sentiment, Dominantie en Volume voor een specifieke user.
    """
    logger.info(f"🧠 [Market-Agent] Start Analysis for user_id={user_id}")

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen DB-verbinding")
        return

    try:
        with conn.cursor() as cur:
            # 1️⃣ HAAL ACTIEVE SYMBOLS OP VOOR DEZE USER
            cur.execute("SELECT DISTINCT symbol FROM setups WHERE user_id = %s", (user_id,))
            symbol_rows = cur.fetchall()
            user_symbols = [r[0].upper() for r in symbol_rows if r[0]]
            
            if not user_symbols:
                user_symbols = ['BTC']

            # 2️⃣ HAAL GLOBALE MARKET DATA OP
            cur.execute("""
                SELECT DISTINCT ON (name)
                    name, value, timestamp
                FROM global_market_indicators
                ORDER BY name, timestamp DESC;
            """)
            indicator_rows = cur.fetchall()

            # Gebruik ANY() om een lijst veilig door te geven aan PostgreSQL
            cur.execute("""
                SELECT symbol, price, volume, change_24h, timestamp
                FROM market_data
                WHERE symbol = ANY(%s)
                ORDER BY timestamp DESC
                LIMIT 10;
            """, (user_symbols,))
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
            ],
            "active_portfolio_symbols": user_symbols
        }

        # 3️⃣ HAAL HISTORISCHE CONTEXT OP (GISTEREN)
        yesterday_insight = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT avg_score, trend, bias, summary
                FROM ai_category_insights
                WHERE user_id = %s AND category = 'market' AND date = CURRENT_DATE - INTERVAL '1 day'
                LIMIT 1;
            """, (user_id,))
            y_row = cur.fetchone()
            if y_row:
                yesterday_insight = {
                    "score": float(y_row[0]) if y_row[0] is not None else 50.0,
                    "trend": y_row[1] or "neutraal",
                    "bias": y_row[2] or "afwachtend",
                    "summary": y_row[3] or ""
                }

        # 4️⃣ BEREID PROMPT VOOR
        system_prompt = build_system_prompt(
            agent="market",
            task="""
Je bent een specialist in crypto-marktsentiment en on-chain data.
Analyseer de huidige marktdynamiek op basis van prijzen, volume en sentiment-indicatoren voor de actieve portfolio assets van de gebruiker.
Geef een heldere conclusie over het huidige momentum.

Houd rekening met de historische context (gisteren). Zorg dat je analyse logisch voortbouwt op gisteren, tenzij de data vandaag een duidelijke kanteling laat zien. Wees consistent in je momentum-bepaling.

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
            "market_snapshot": market_snapshot,
            "historical_context": yesterday_insight or "Geen eerdere data beschikbaar.",
            "analysis_date": date.today().isoformat()
        }

        # 5️⃣ AI CALL & PARSING
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # Defensieve fallback
        fallback_score = yesterday_insight["score"] if yesterday_insight else 50.0
        fallback_trend = yesterday_insight["trend"] if yesterday_insight else "neutraal"
        fallback_bias = yesterday_insight["bias"] if yesterday_insight else "afwachtend"

        if not isinstance(raw_ai_response, dict):
            logger.warning(f"⚠️ [Market-Agent] AI response geen dict, fallback gebruikt. Response: {raw_ai_response}")
            raw_ai_response = {
                "score": fallback_score,
                "trend": fallback_trend,
                "bias": fallback_bias,
                "risk": "gemiddeld",
                "summary": "Data verwerking mislukt. Vorige context overgenomen.",
                "top_signals": []
            }

        # Score clampen tussen 0 en 100
        safe_score = _clamp_score(raw_ai_response.get("score"), default=fallback_score)

        # 6️⃣ OPSLAAN IN AI_CATEGORY_INSIGHTS (waar dashboard naar kijkt)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights
                    (user_id, category, avg_score, trend, bias, risk, summary, top_signals, date)
                VALUES (%s, 'market', %s, %s, %s, %s, %s, %s, CURRENT_DATE)
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
                safe_score,
                str(raw_ai_response.get("trend", fallback_trend)),
                str(raw_ai_response.get("bias", fallback_bias)),
                str(raw_ai_response.get("risk", "gemiddeld")),
                str(raw_ai_response.get("summary", "")),
                json.dumps(raw_ai_response.get("top_signals", [])),
            ))

        conn.commit()
        logger.info(f"✅ [Market-Agent] Analysis voltooid voor user_id={user_id} | Score: {safe_score} | Symbols: {user_symbols}")

    except Exception:
        if conn: conn.rollback()
        logger.error(f"❌ [Market-Agent] Fout tijdens run voor user_id={user_id}", exc_info=True)
    finally:
        if conn: conn.close()
