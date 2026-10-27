import logging
import math
from datetime import datetime, timedelta, timezone
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


def score_source_is_fresh(category: str, indicator: str, timestamp: Any, *,
                          symbol: str = "BTC", now: datetime | None = None) -> bool:
    """Apply source-specific age limits before a score can size Smart DCA.

    Monthly macro releases remain usable through their next release window;
    daily sources have a weekend allowance. Crypto technical/market data is
    expected more frequently than exchange-traded asset data.
    """
    if not isinstance(timestamp, datetime):
        return False
    current = now or datetime.now(timezone.utc)
    observed = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp.astimezone(timezone.utc)
    if category == "macro" and normalize_indicator_name(indicator) in {"interest_rate", "inflation_rate"}:
        # FRED stamps monthly series with the period start, which precedes
        # publication by weeks. Allow the current release window, not a new
        # receipt timestamp on each fetch.
        limit = timedelta(days=75)
    elif category == "macro":
        limit = timedelta(days=4)
    elif category in {"technical", "market"}:
        from backend.services.asset_catalog_service import DEFAULT_ASSET_CATALOG
        asset_class = DEFAULT_ASSET_CATALOG.get(str(symbol).upper(), {}).get("asset_class")
        limit = timedelta(hours=36 if asset_class == "crypto" else 96)
    else:
        return False
    age = current - observed
    return timedelta(0) <= age <= limit

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


def score_exact_market_measurement(category: str, name: str, value: float,
                                   user_id: int, symbol: str, market_id: int) -> dict:
    """Apply the existing Score 2.0 rules to one verified pair measurement."""
    from backend.utils.market_interpreter import normalize_market_value_with_history
    from backend.utils.technical_interpreter import normalize_technical_value_for_rules
    from backend.utils.scoring_engine import score_indicator

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("exact_market_scoring_database_unavailable")
    try:
        if category == "market":
            normalized = normalize_market_value_with_history(
                conn, symbol, name, value, market_id=market_id)
        else:
            normalized = normalize_technical_value_for_rules(
                conn, name, value, user_id, symbol, market_id=market_id)
        if normalized is None:
            return {"score": None, "trend": None, "interpretation": None, "action": None}
        result = score_indicator(
            conn, category, name, normalized, user_id=user_id,
            symbol=symbol, market_id=market_id)
        if result.get("rule_origin") not in {"custom", "system_template"}:
            return {"score": None, "trend": None, "interpretation": None, "action": None}
        return result
    finally:
        conn.close()


def score_snapshot_diagnosis(category: str, symbol: str, configurations,
                             readings, evidence, calculated_at) -> str:
    """Explain why a saved category cannot currently be used as a score.

    Source freshness alone is insufficient after a user changes indicator
    rules or a provider publishes a new value before the next score job.
    """
    if not isinstance(calculated_at, datetime) or not isinstance(evidence, dict):
        return "score_unverified"
    calculation_time = (calculated_at.replace(tzinfo=timezone.utc)
                        if calculated_at.tzinfo is None else calculated_at.astimezone(timezone.utc))
    configured = {}
    for name, updated_at in configurations:
        key = normalize_indicator_name(name)
        if not isinstance(updated_at, datetime):
            return "configuration_unverified"
        update_time = (updated_at.replace(tzinfo=timezone.utc)
                       if updated_at.tzinfo is None else updated_at.astimezone(timezone.utc))
        if update_time > calculation_time:
            return "score_rebuild_pending"
        configured[key] = True
    if not configured or set(evidence) != set(configured):
        return "score_rebuild_pending"
    current = {normalize_indicator_name(name): (value, observed_at)
               for name, value, observed_at in readings
               if normalize_indicator_name(name) in configured}
    if set(current) != set(configured):
        return "missing_indicator_reading"
    for name, (value, observed_at) in current.items():
        saved = evidence.get(name)
        if not isinstance(saved, dict):
            return "score_rebuild_pending"
        if value is None:
            return "missing_indicator_reading"
        if not score_source_is_fresh(category, name, observed_at, symbol=symbol):
            return "stale_source" if observed_at is not None else "missing_indicator_reading"
        # Legacy daily rows could contain a generated bucket score. The
        # provenance field is mandatory for a current decision-grade score.
        if saved.get("rule_origin") not in {"custom", "system_template"}:
            return "rule_unverified"
        try:
            if not math.isclose(float(saved["value"]), float(value), rel_tol=1e-12):
                return "score_rebuild_pending"
        except (KeyError, TypeError, ValueError):
            return "score_rebuild_pending"
        if saved.get("source_observed_at") != observed_at.isoformat():
            return "score_rebuild_pending"
    return "fresh"


def score_snapshot_is_current(category: str, symbol: str, configurations,
                              readings, evidence, calculated_at) -> bool:
    """Keep the report and bot gate on the same strict verification rule."""
    return score_snapshot_diagnosis(
        category, symbol, configurations, readings, evidence, calculated_at,
    ) == "fresh"


# =========================================================
# 🔢 SCORE ENGINE (USER-AWARE)
# =========================================================
def generate_scores_db(category: str, user_id: Optional[int] = None, symbol: str = "BTC",
                       *, market_id: int | None = None) -> Dict[str, Any]:
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
        return {"scores": {}, "total_score": None, "top_contributors": []}

    try:
        with conn.cursor() as cur:
            # The owner's asset indicator choices apply to both exact quotes.
            # A pair-specific choice overrides the same base indicator when
            # one is explicitly configured; it is never inferred as a price.
            config_scope = "AND (market_id = %s OR market_id IS NULL)" if market_id is not None else "AND market_id IS NULL"
            cur.execute(f"""
                SELECT indicator FROM user_indicator_configs
                WHERE user_id = %s AND category = %s AND symbol = %s
                  AND enabled = TRUE {config_scope}
            """, (user_id, category, symbol, market_id) if market_id is not None
                 else (user_id, category, symbol))
            configured = {normalize_indicator_name(row[0]) for row in cur.fetchall()}
            if not configured:
                return {"scores": {}, "total_score": None, "top_contributors": [],
                        "source_status": "missing_configuration"}
            # Macro measurements are global to the owner, while the owner's
            # selected macro indicators and weights remain asset-scoped.
            source_scope = (
                "AND market_id = %s" if market_id is not None
                else "AND market_id IS NULL AND symbol = %s"
            )
            if category == "macro":
                source_scope = ""
            cur.execute(f"""
                SELECT DISTINCT ON ({name_col}) {name_col}, value, source_observed_at
                FROM {data_table}
                WHERE user_id = %s {source_scope}
                ORDER BY {name_col}, source_observed_at DESC NULLS LAST, timestamp DESC NULLS LAST
            """, (user_id,) if category == "macro" else
                  ((user_id, market_id) if market_id is not None else (user_id, symbol)))
            rows = {normalize_indicator_name(row[0]): row for row in cur.fetchall()
                    if normalize_indicator_name(row[0]) in configured}

        # A newly stamped daily_scores row must not launder an old component
        # into fresh trading evidence. Fail the whole component rather than
        # silently reweighting it around missing/stale configured indicators.
        if set(rows) != configured or any(
            row[1] is None or not score_source_is_fresh(category, row[0], row[2], symbol=symbol)
            for row in rows.values()
        ):
            logger.warning("Stale %s score inputs for user=%s symbol=%s", category, user_id, symbol)
            return {"scores": {}, "total_score": None, "top_contributors": [],
                    "source_status": "missing_or_stale_indicator"}
        data = {name: (float(row[1]), row[2]) for name, row in rows.items()}

        if not data:
            logger.warning(f"⚠️ Geen data voor {category} (user_id={user_id})")
            return {"scores": {}, "total_score": None, "top_contributors": []}

        scores: Dict[str, Any] = {}
        weighted_total = 0.0
        total_weight = 0.0

        # Import here: interpreters also use scoring_utils for rule lookups.
        from backend.utils.macro_interpreter import normalize_macro_value_with_history
        from backend.utils.market_interpreter import normalize_market_value_with_history
        from backend.utils.technical_interpreter import normalize_technical_value_for_rules
        for indicator, (value, observed_at) in data.items():
            logger.info(f"DEBUG: Scoring {category} indicator: {indicator} = {value}")
            if category == "market":
                normalized_value = normalize_market_value_with_history(
                    conn, symbol, indicator, value, market_id=market_id,
                )
            elif category == "macro":
                normalized_value = normalize_macro_value_with_history(conn, user_id, indicator, value)
            else:
                normalized_value = normalize_technical_value_for_rules(
                    conn, indicator, value, user_id, symbol, market_id=market_id,
                )
            if normalized_value is None:
                return {"scores": {}, "total_score": None, "top_contributors": [],
                        "source_status": "insufficient_indicator_history"}
            scored = score_indicator(
                conn=conn,
                category=category,
                indicator=indicator,
                value=normalized_value,
                user_id=user_id,
                symbol=symbol,
                market_id=market_id,
            )
            if scored.get("rule_origin") in {"missing", "generated_fallback"}:
                return {"scores": {}, "total_score": None, "top_contributors": [],
                        "source_status": "missing_rule"}
            weight = float(scored.get("weight", 1))

            scores[indicator] = {
                "value": value,
                "normalized_value": normalized_value,
                "source_observed_at": observed_at.isoformat(),
                "score": scored["score"],
                "trend": scored["trend"],
                "interpretation": scored["interpretation"],
                "action": scored["action"],
                "weight": weight,
                "mode": scored["score_mode"],
                "rule_origin": scored["rule_origin"],
            }

            weighted_total += scored["score"] * weight
            total_weight += weight

        avg_score = round(weighted_total / total_weight) if total_weight else None

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
            "source_status": "available" if total_weight > 0 else "missing_weight",
        }

    except Exception:
        logger.exception(f"❌ Score generatie fout ({category})")
        return {"scores": {}, "total_score": None, "top_contributors": []}

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
