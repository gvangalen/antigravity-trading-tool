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
            {"indicator": ind, "value": float(v) if v is not None else None, "timestamp": ts.isoformat() if ts else None}
            for ind, v, ts in rows
        ]

        # Pre-filter tegen context-overflow: cap op 20 indicatoren
        tech_snapshot = tech_snapshot[:20]

        # 2️⃣ HAAL HISTORISCHE CONTEXT OP (GISTEREN)
        yesterday_insight = None
        with conn.cursor() as cur:
            cur.execute("""
                SELECT avg_score, trend, bias, summary
                FROM ai_category_insights
                WHERE user_id = %s AND category = 'technical' AND symbol = 'GLOBAL'
                  AND date = CURRENT_DATE - INTERVAL '1 day'
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

        # 3️⃣ BEREID PROMPT VOOR
        system_prompt = build_system_prompt(
            agent="technical",
            task="""
Je bent een technisch analist gespecialiseerd in prijsactie, indicatoren en marktstructuur.
Analyseer de technische staat van de actieve markt voor deze portfolio. Focus op de top technische indicatoren.
Vat samen of we in een overbought/oversold conditie zitten en wat de meest waarschijnlijke richting is op korte termijn.

Houd rekening met de historische context (gisteren). Zorg dat je analyse logisch voortbouwt op gisteren, tenzij de indicatoren vandaag een duidelijke omslag laten zien. Wees consistent.

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
            "technical_snapshot": tech_snapshot,
            "historical_context": yesterday_insight or "Geen eerdere data beschikbaar.",
            "analysis_date": date.today().isoformat()
        }

        # 4️⃣ AI CALL & PARSING
        raw_ai_response = ask_gpt_json(
            prompt=json.dumps(payload, ensure_ascii=False, indent=2),
            system_role=system_prompt
        )

        # Defensieve fallback
        fallback_score = yesterday_insight["score"] if yesterday_insight else 50.0
        fallback_trend = yesterday_insight["trend"] if yesterday_insight else "neutraal"
        fallback_bias = yesterday_insight["bias"] if yesterday_insight else "afwachtend"

        if not isinstance(raw_ai_response, dict):
            logger.warning(f"⚠️ [Technical-Agent] AI response geen dict, fallback gebruikt. Response: {raw_ai_response}")
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

        # 5️⃣ OPSLAAN IN AI_CATEGORY_INSIGHTS (waar dashboard naar kijkt)
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights
                    (user_id, category, symbol, avg_score, trend, bias, risk, summary, top_signals, date)
                VALUES (%s, 'technical', 'GLOBAL', %s, %s, %s, %s, %s, %s, CURRENT_DATE)
                ON CONFLICT (user_id, category, symbol, date)
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
        logger.info(f"✅ [Technical-Agent] Analysis voltooid voor user_id={user_id} | Score: {safe_score}")

    except Exception:
        if conn: conn.rollback()
        logger.error(f"❌ [Technical-Agent] Fout tijdens run voor user_id={user_id}", exc_info=True)
    finally:
        if conn: conn.close()
