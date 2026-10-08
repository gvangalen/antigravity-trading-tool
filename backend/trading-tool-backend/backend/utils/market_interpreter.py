import logging
from statistics import median
from backend.utils.scoring_utils import (
    get_score_rule_from_db,
    normalize_indicator_name,
)

logger = logging.getLogger(__name__)

MARKET_INDICATOR_MAP = {
    "price": "btc_price",
    "change_24h": "btc_change_24h",
    "volume": "btc_volume",
    "price_trend": "price_trend",
    "volatility": "volatility",
    "volume_strength": "volume_strength",
}


# =========================================================
# 🔹 Normalisatie naar 0–100 (Optie B)
# =========================================================
def normalize_market_value(indicator: str, value: float) -> float:
    """
    Zet raw market value om naar genormaliseerde 0–100 schaal.
    Alles wordt uniform en UX-proof.
    (Magnitude-based design is bewust gekozen.)
    """

    try:
        if value is None:
            return 0

        value = float(value)

        # -------------------------------------------------
        # BTC Volume (% afwijking t.o.v. 30d gemiddelde)
        # -------------------------------------------------
        if indicator in {"btc_volume", "volume_change"}:
            abs_dev = abs(value)
            cap = 80  # 80% afwijking = extreem
            return min(100, (abs_dev / cap) * 100)

        # -------------------------------------------------
        # 24h price change (%)
        # -------------------------------------------------
        if indicator in {"btc_change_24h", "change_24h"}:
            # Preserve direction: -20% maps to 0, unchanged to 50,
            # +20% to 100. Absolute magnitude made drops and rallies equal.
            return max(0, min(100, 50 + value * 2.5))

        # -------------------------------------------------
        # Volatility (%)
        # -------------------------------------------------
        if indicator == "volatility":
            abs_dev = abs(value)
            cap = 15
            return min(100, (abs_dev / cap) * 100)

        # -------------------------------------------------
        # Price trend / volume strength (al 0–100)
        # -------------------------------------------------
        if indicator in ["price_trend", "volume_strength"]:
            return max(0, min(100, value))

        # -------------------------------------------------
        # Fallback
        # -------------------------------------------------
        return max(0, min(100, value))

    except Exception:
        logger.error("❌ Normalisatie fout", exc_info=True)
        return 0


def normalize_market_value_with_history(conn, symbol: str, indicator: str,
                                        value: float) -> float | None:
    """Use asset-relative context for absolute price and volume readings.

    A EUR or USD price and a trading volume are not percentages. Without a
    measured history they cannot safely select one of the 0–100 rule buckets.
    """
    if indicator not in {"price", "volume"}:
        return normalize_market_value(indicator, value)
    column = "price" if indicator == "price" else "volume"
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT DISTINCT ON (source_observed_at::date) {column}
            FROM market_data
            WHERE symbol = %s AND source_observed_at >= NOW() - INTERVAL '30 days'
              AND source_observed_at IS NOT NULL AND {column} IS NOT NULL
            ORDER BY source_observed_at::date, source_observed_at DESC
        """, (symbol,))
        history = [float(row[0]) for row in cur.fetchall()]
    if len(history) < 5:
        return None
    current = float(value)
    if indicator == "price":
        low, high = min(history), max(history)
        return 50.0 if high == low else max(0.0, min(100.0, 100 * (current - low) / (high - low)))
    typical = median(history)
    if typical <= 0:
        return None
    return max(0.0, min(100.0, 50 * current / typical))


# =========================================================
# 🔹 Market Interpreter (USER-AWARE)
# =========================================================
def interpret_market_indicator(indicator: str, value: float, user_id: int):
    """
    Interpreteert market indicator via centrale DB scoreregels.
    Flow:
    raw_value → normalized_value (0–100) → DB rules → score

    ✅ User-based rules supported
    """

    try:
        if value is None:
            return _fallback("Geen waarde beschikbaar")

        indicator = (indicator or "").strip().lower()

        mapped = MARKET_INDICATOR_MAP.get(indicator, indicator)
        normalized_name = normalize_indicator_name(mapped)

        logger.debug(
            f"Market interpret → {indicator} → {normalized_name} raw={value}"
        )

        # 🔹 Stap 1: normaliseren naar 0–100
        normalized_value = normalize_market_value(normalized_name, value)

        logger.debug(
            f"Normalized value (0–100): {normalized_value}"
        )

        # 🔹 Stap 2: user-aware rule lookup
        rule = get_score_rule_from_db(
            "market",
            normalized_name,
            normalized_value,
            user_id=user_id,  # ✅ FIX: user_id meegeven
        )

        if not rule or rule.get("score") is None:
            logger.warning(
                f"⚠️ Geen rule match → {normalized_name} value={normalized_value}"
            )
            return _fallback("Geen scoreregel beschikbaar")

        return {
            "score": max(0, min(100, rule["score"])),
            "trend": rule.get("trend") or "neutral",
            "interpretation": rule.get("interpretation")
                or "Geen interpretatie beschikbaar",
            "action": rule.get("action") or "Geen actie",
        }

    except Exception:
        logger.error("❌ interpret_market_indicator fout", exc_info=True)
        return _fallback("Interpretatiefout")


# =========================================================
# 🔹 Fallback helper
# =========================================================
def _fallback(reason: str):
    return {
        "score": None,
        "trend": None,
        "interpretation": reason,
        "action": "Geen actie",
    }
