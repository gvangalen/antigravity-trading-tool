import logging
from typing import Dict, Any, List, Optional

from backend.utils.db import get_db_connection
from backend.utils.scoring_engine import score_indicator

# =========================================================
# ⚙️ Logging
# =========================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# =========================================================
# 🧩 Naam-aliases
# =========================================================
NAME_ALIASES = {
    "fear_and_greed_index": "fear_greed_index",
    "fear_greed": "fear_greed_index",
    "sandp500": "sp500",
    "s&p500": "sp500",
    "s&p_500": "sp500",
    "sp_500": "sp500",
}

def normalize_indicator_name(name: str) -> str:
    normalized = (
        name.lower()
        .replace("&", "and")
        .replace("s&p", "sp")
        .replace(" ", "_")
        .replace("-", "_")
        .strip()
    )
    return NAME_ALIASES.get(normalized, normalized)


# =========================================================
# 🔢 SCORE ENGINE (USER-AWARE)
# =========================================================
def generate_scores_db(category: str, user_id: Optional[int] = None, symbol: str = "BTC") -> Dict[str, Any]:
    """
    Universele score-engine voor:
    - macro
    - technical
    - market

    ✅ User-based rules supported
    ✅ Global mode (user_id=None) supported
    """

    table_map = {
        "macro": ("macro_data", "name"),
        "technical": ("technical_indicators", "indicator"),
        "market": ("market_data_indicators", "name"),
    }

    if category not in table_map:
        raise ValueError(f"❌ Onbekende category: {category}")

    data_table, name_col = table_map[category]

    conn = get_db_connection()
    if not conn:
        return {"scores": {}, "total_score": 10, "top_contributors": []}

    try:
        with conn.cursor() as cur:
            # ✅ NEW: Use Global Config if available
            if user_id is not None and category == "technical":
                # Haal eerst de config op
                cur.execute("""
                    SELECT indicator FROM user_indicator_configs
                    WHERE user_id = %s
                      AND category = %s
                      AND symbol = %s
                      AND enabled = TRUE
                """, (user_id, category, symbol))
                configs = [r[0] for r in cur.fetchall()]
                
                if configs:
                    # Haal nu de data op voor deze specifieke indicators en dit symbool
                    cur.execute(f"""
                        SELECT DISTINCT ON ({name_col}) {name_col}, value
                        FROM {data_table}
                        WHERE user_id = %s AND symbol = %s AND {name_col} = ANY(%s)
                        ORDER BY {name_col}, timestamp DESC
                    """, (user_id, symbol, configs))
                else:
                    # Missing canonical preferences are not permission to score
                    # unrelated indicator data for this user and asset.
                    return {"scores": {}, "total_score": 10, "top_contributors": []}
            
            elif user_id is not None:
                if category == "macro":
                    cur.execute(f"""
                        SELECT DISTINCT ON ({name_col}) {name_col}, value
                        FROM {data_table}
                        WHERE user_id = %s
                        ORDER BY {name_col}, timestamp DESC
                    """, (user_id,))
                else:
                    cur.execute(f"""
                        SELECT DISTINCT ON ({name_col}) {name_col}, value
                        FROM {data_table}
                        WHERE user_id = %s AND symbol = %s
                        ORDER BY {name_col}, timestamp DESC
                    """, (user_id, symbol))
            else:
                # 🌍 GLOBAL mode (fallback)
                pass

            rows = cur.fetchall()

        data = {
            normalize_indicator_name(r[0]): float(r[1])
            for r in rows if r[1] is not None
        }

        if not data:
            logger.warning(f"⚠️ Geen data voor {category} (user_id={user_id})")
            return {"scores": {}, "total_score": 10, "top_contributors": []}

        scores: Dict[str, Any] = {}
        weighted_total = 0.0
        total_weight = 0.0

        for indicator, value in data.items():
            logger.info(f"DEBUG: Scoring {category} indicator: {indicator} = {value}")
            # ✅ CRUCIAAL: user_id meegeven
            scored = score_indicator(
                conn=conn,
                category=category,
                indicator=indicator,
                value=value,
                user_id=user_id,   # ← NIEUW
            )

            weight = float(scored.get("weight", 1))

            scores[indicator] = {
                "value": value,
                "score": scored["score"],
                "trend": scored["trend"],
                "interpretation": scored["interpretation"],
                "action": scored["action"],
                "weight": weight,
                "mode": scored["score_mode"],
            }

            weighted_total += scored["score"] * weight
            total_weight += weight

        avg_score = round(weighted_total / total_weight) if total_weight else 10

        top_contributors: List[str] = [
            name for name, _ in sorted(
                scores.items(),
                key=lambda x: x[1]["score"] * x[1]["weight"],
                reverse=True
            )
        ][:3]

        return {
            "scores": scores,
            "total_score": avg_score,
            "top_contributors": top_contributors,
        }

    except Exception:
        logger.exception(f"❌ Score generatie fout ({category})")
        return {"scores": {}, "total_score": 10, "top_contributors": []}

    finally:
        conn.close()


# =========================================================
# 🔗 DASHBOARD: DAILY COMBINED SCORES
# =========================================================
def get_scores_for_symbol(user_id: int, symbol: str = "BTC", include_metadata: bool = False) -> Dict[str, Any]:

    conn = get_db_connection()
    if not conn:
        return {}

    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    macro_score,
                    macro_interpretation,
                    macro_top_contributors,

                    technical_score,
                    technical_interpretation,
                    technical_top_contributors,

                    market_score,
                    market_interpretation,
                    market_top_contributors,

                    setup_score
                FROM daily_scores
                WHERE user_id = %s
                  AND report_date = CURRENT_DATE
                  AND symbol = %s
                LIMIT 1
            """, (user_id, symbol))
            row = cur.fetchone()

        if not row:
            return {}

        return {
            "macro_score": row[0],
            "macro_interpretation": row[1],
            "macro_top_contributors": row[2] or [],

            "technical_score": row[3],
            "technical_interpretation": row[4],
            "technical_top_contributors": row[5] or [],

            "market_score": row[6],
            "market_interpretation": row[7],
            "market_top_contributors": row[8] or [],

            "setup_score": row[9],
        }

    finally:
        conn.close()


# =========================================================
# 🔁 BACKWARD COMPATIBILITY (CELERY SAFE)
# =========================================================
def get_score_rule_from_db(category: str, indicator: str, value, user_id: int):
    """
    Oude modules verwachten deze functie.
    Nu user-aware.
    """

    conn = get_db_connection()
    if not conn:
        return None

    try:
        result = score_indicator(
            conn=conn,
            category=category,
            indicator=normalize_indicator_name(indicator),
            value=value,
            user_id=user_id,   # ✅ ook hier user-id meegeven
        )

        return {
            "score": result.get("score"),
            "trend": result.get("trend"),
            "interpretation": result.get("interpretation"),
            "action": result.get("action"),
        }

    except Exception:
        logger.exception("❌ get_score_rule_from_db wrapper error")
        return None
    finally:
        conn.close()
