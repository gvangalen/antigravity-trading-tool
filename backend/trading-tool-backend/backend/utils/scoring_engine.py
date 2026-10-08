# backend/utils/scoring_engine.py
import logging
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.utils.db import get_db_connection

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ============================================================
# Fixed buckets (UX/engine contract)
# ============================================================
FIXED_BUCKETS: List[Tuple[float, float]] = [
    (0.0, 20.0),
    (20.0, 40.0),
    (40.0, 60.0),
    (60.0, 80.0),
    (80.0, 100.0),
]

# Default “standard” scores per bucket (kan je later aanpassen)
DEFAULT_BUCKET_SCORES: List[int] = [10, 25, 50, 75, 100]


# ============================================================
# Types
# ============================================================
@dataclass
class RuleRow:
    id: int
    indicator: str
    range_min: float
    range_max: float
    score: int
    trend: Optional[str]
    interpretation: Optional[str]
    action: Optional[str]
    score_mode: str
    is_active: bool
    weight: float
    user_id: Optional[int] = None  # ✅ nieuw: template (NULL) vs user override


# ============================================================
# Helpers
# ============================================================
def _to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _clamp_score(v: int) -> int:
    # jij wil geen 0 — minimaal 10
    if v < 10:
        return 10
    if v > 100:
        return 100
    return v


def _apply_score_mode(score: int, score_mode: str) -> int:
    """
    - standard: score zoals rule
    - contrarian: 100 - score
    - custom: score zoals rule (custom rules zijn al "eigen")
    """
    s = _clamp_score(score)
    mode = (score_mode or "standard").strip().lower()

    if mode == "contrarian":
        return _clamp_score(100 - s)

    return s


def _table_names(category: str) -> Tuple[str, str]:
    """
    Returns: (rules_table, scores_table)
    """
    c = category.strip().lower()
    if c not in ("macro", "market", "technical"):
        raise ValueError("category must be: macro | market | technical")
    return (f"{c}_indicator_rules", f"{c}_indicator_scores")


# ============================================================
# Bucket enforcement (server-side contract)
# ============================================================
def _bucket_key(rmin: float, rmax: float) -> Tuple[float, float]:
    return (round(float(rmin), 4), round(float(rmax), 4))


def _fallback_fixed_rules(indicator: str, score_mode: str = "standard", weight: float = 1.0) -> List[RuleRow]:
    out: List[RuleRow] = []
    for i, (bmin, bmax) in enumerate(FIXED_BUCKETS):
        out.append(
            RuleRow(
                id=-1,
                indicator=indicator,
                range_min=bmin,
                range_max=bmax,
                score=DEFAULT_BUCKET_SCORES[i],
                trend=None,
                interpretation="Fallback bucket rule (auto).",
                action="Geen actie.",
                score_mode=score_mode,
                is_active=True,
                weight=weight,
                user_id=None,
            )
        )
    return out


def _force_fixed_buckets(indicator: str, rules: List[RuleRow]) -> List[RuleRow]:
    """
    Zorgt dat rules altijd EXACT 5 buckets zijn:
      0–20 / 20–40 / 40–60 / 60–80 / 80–100
    """
    if not rules:
        return _fallback_fixed_rules(indicator)

    # Neem score_mode/weight uit eerste rule (contract: consistent per indicator)
    first_mode = (rules[0].score_mode or "standard").strip().lower()
    first_weight = float(rules[0].weight if rules[0].weight is not None else 1.0)

    # map bestaande rules per bucket (alleen als bucket exact matcht)
    by_bucket: Dict[Tuple[float, float], RuleRow] = {}
    for r in rules:
        k = _bucket_key(r.range_min, r.range_max)
        if k in by_bucket:
            continue
        by_bucket[k] = r

    out: List[RuleRow] = []
    for i, (bmin, bmax) in enumerate(FIXED_BUCKETS):
        k = _bucket_key(bmin, bmax)

        if k in by_bucket:
            r = by_bucket[k]
            out.append(
                RuleRow(
                    id=int(r.id),
                    indicator=r.indicator,
                    range_min=bmin,
                    range_max=bmax,
                    score=int(r.score),
                    trend=r.trend,
                    interpretation=r.interpretation,
                    action=r.action,
                    score_mode=str(r.score_mode or first_mode),
                    is_active=bool(r.is_active),
                    weight=float(r.weight if r.weight is not None else first_weight),
                    user_id=r.user_id,
                )
            )
        else:
            # ontbrekende bucket → fallback invullen (maar wel mode/weight consistent houden)
            out.append(
                RuleRow(
                    id=-1,
                    indicator=indicator,
                    range_min=bmin,
                    range_max=bmax,
                    score=DEFAULT_BUCKET_SCORES[i],
                    trend=None,
                    interpretation="Bucket ontbreekt in DB (fallback).",
                    action="Geen actie.",
                    score_mode=first_mode,
                    is_active=True,
                    weight=first_weight,
                    user_id=None,
                )
            )

    return out


# ============================================================
# DB: Rules (USER override + TEMPLATE fallback)
# ============================================================
def fetch_rules_for_indicator(
    conn,
    category: str,
    indicator: str,
    user_id: Optional[int] = None,  # ✅ nieuw
    only_active: bool = True,
    enforce_fixed_buckets: bool = True,
    symbol: Optional[str] = None,
) -> List[RuleRow]:
    rules_table, _ = _table_names(category)
    indicator = (indicator or "").strip()
    if not indicator:
        return []

    def _run_query(where_user_sql: str, params: tuple) -> List[tuple]:
        with conn.cursor() as cur:
            if only_active:
                cur.execute(
                    f"""
                    SELECT
                        id,
                        indicator,
                        range_min,
                        range_max,
                        score,
                        trend,
                        interpretation,
                        action,
                        COALESCE(score_mode, 'standard') AS score_mode,
                        COALESCE(is_active, TRUE)        AS is_active,
                        COALESCE(weight, 1)              AS weight,
                        user_id
                    FROM {rules_table}
                    WHERE indicator = %s
                      AND {where_user_sql}
                      AND COALESCE(is_active, TRUE) = TRUE
                    ORDER BY range_min ASC, range_max ASC, id ASC
                    """,
                    params,
                )
            else:
                cur.execute(
                    f"""
                    SELECT
                        id,
                        indicator,
                        range_min,
                        range_max,
                        score,
                        trend,
                        interpretation,
                        action,
                        COALESCE(score_mode, 'standard') AS score_mode,
                        COALESCE(is_active, TRUE)        AS is_active,
                        COALESCE(weight, 1)              AS weight,
                        user_id
                    FROM {rules_table}
                    WHERE indicator = %s
                      AND {where_user_sql}
                    ORDER BY range_min ASC, range_max ASC, id ASC
                    """,
                    params,
                )
            return cur.fetchall()

    # Asset-scoped product settings are authoritative when an asset is known.
    # Legacy user rules have no asset identity and must not override them.
    if user_id is not None and symbol:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, config_json, priority FROM user_indicator_configs
                   WHERE user_id = %s AND symbol = %s AND category = %s
                     AND LOWER(indicator) = LOWER(%s) AND enabled = TRUE
                   LIMIT 1""",
                (user_id, symbol.upper(), category, indicator),
            )
            config = cur.fetchone()
        if config is None:
            # An indicator may be scored while its new selection is still in
            # the writer's uncommitted transaction. Daily aggregation itself
            # requires a committed canonical selection.
            rows = _run_query("user_id IS NULL", (indicator,))
            template = [RuleRow(
                id=int(row[0]), indicator=str(row[1]), range_min=float(row[2]),
                range_max=float(row[3]), score=int(row[4]), trend=row[5],
                interpretation=row[6], action=row[7], score_mode="standard",
                is_active=bool(row[9]), weight=1.0, user_id=None,
            ) for row in rows]
            return _force_fixed_buckets(indicator, template) if enforce_fixed_buckets else template
        config_id, metadata, priority = config
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}
        metadata = metadata if isinstance(metadata, dict) else {}
        mode = str(metadata.get("score_mode") or "standard").lower()
        try:
            weight = float(metadata.get("weight", float(priority or 100) / 100))
        except (TypeError, ValueError):
            weight = 1.0
        weight = max(0.0, min(weight, 3.0))
        configured_rules = metadata.get("rules") if mode == "custom" else None
        if mode == "custom" and not configured_rules:
            return []
        if configured_rules:
            rules = []
            for item in configured_rules:
                if not isinstance(item, dict):
                    continue
                try:
                    rules.append(RuleRow(
                        id=int(config_id), indicator=indicator,
                        range_min=float(item["range_min"]), range_max=float(item["range_max"]),
                        score=int(item["score"]), trend=item.get("trend"),
                        interpretation=item.get("interpretation"), action=item.get("action"),
                        score_mode="custom", is_active=True, weight=weight, user_id=user_id,
                    ))
                except (KeyError, TypeError, ValueError):
                    return []
            if len(rules) != len(FIXED_BUCKETS) or {
                _bucket_key(rule.range_min, rule.range_max) for rule in rules
            } != {_bucket_key(*bucket) for bucket in FIXED_BUCKETS}:
                return []
            return sorted(rules, key=lambda rule: rule.range_min)
        # Only system templates supply standard/contrarian bucket values.
        rows = _run_query("user_id IS NULL", (indicator,))
        rules = [RuleRow(
            id=int(row[0]), indicator=str(row[1]), range_min=float(row[2]),
            range_max=float(row[3]), score=int(row[4]), trend=row[5],
            interpretation=row[6], action=row[7], score_mode=mode,
            is_active=bool(row[9]), weight=weight, user_id=user_id,
        ) for row in rows]
        if not rules:
            rules = _fallback_fixed_rules(indicator, mode, weight)
        return _force_fixed_buckets(indicator, rules) if enforce_fixed_buckets else rules

    # Legacy callers without an asset retain their old behavior.
    # 1️⃣ user rules eerst
    rows: List[tuple] = []
    if user_id is not None:
        rows = _run_query("user_id = %s", (indicator, user_id))

    # 2️⃣ fallback template (NULL)
    if not rows:
        rows = _run_query("user_id IS NULL", (indicator,))

    rules: List[RuleRow] = []
    for r in rows:
        rules.append(
            RuleRow(
                id=int(r[0]),
                indicator=str(r[1]),
                range_min=float(r[2]),
                range_max=float(r[3]),
                score=int(r[4]),
                trend=r[5],
                interpretation=r[6],
                action=r[7],
                score_mode=str(r[8] or "standard"),
                is_active=bool(r[9]),
                weight=float(r[10] if r[10] is not None else 1.0),
                user_id=int(r[11]) if r[11] is not None else None,
            )
        )

    if enforce_fixed_buckets:
        return _force_fixed_buckets(indicator, rules)

    return rules


def pick_rule_for_value(rules: List[RuleRow], value: Optional[float]) -> Optional[RuleRow]:
    """
    Matcht op:
      range_min <= value < range_max
    Laatste bucket: inclusive max.
    """
    if value is None or not rules:
        return None

    last_index = len(rules) - 1
    for idx, rule in enumerate(rules):
        if idx == last_index:
            if rule.range_min <= value <= rule.range_max:
                return rule
        else:
            if rule.range_min <= value < rule.range_max:
                return rule
    return None


# ============================================================
# Scoring (single indicator)
# ============================================================
def score_indicator(
    conn,
    category: str,
    indicator: str,
    value: Any,
    user_id: Optional[int] = None,  # ✅ nieuw
    symbol: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Engine contract:
    - value hoort NORMALIZED 0–100 te zijn.
    - wij clampen voor safety.
    """
    v_raw = _to_float(value)
    v = None if v_raw is None else _clamp(v_raw, 0.0, 100.0)

    rules = fetch_rules_for_indicator(
        conn,
        category=category,
        indicator=indicator,
        user_id=user_id,
        only_active=True,
        enforce_fixed_buckets=True,
        symbol=symbol,
    )
    rule = pick_rule_for_value(rules, v)

    if not rule:
        return {
            "indicator": indicator,
            "value": v,
            "base_score": None,
            "score": None,
            "score_mode": "standard",
            "weight": 1.0,
            "trend": None,
            "interpretation": "Geen scoreregel match (fallback).",
            "action": "Geen actie.",
            "matched_rule_id": None,
            "rule_origin": "missing",
        }

    generated_fallback = rule.id < 0
    base_score = None if generated_fallback else _clamp_score(int(rule.score))
    final_score = None if generated_fallback else _apply_score_mode(base_score, rule.score_mode)

    w = float(rule.weight if rule.weight is not None else 1.0)
    if w < 0:
        w = 1.0

    return {
        "indicator": indicator,
        "value": v,
        "base_score": base_score,
        "score": final_score,
        "score_mode": rule.score_mode,
        "weight": w,
        "trend": rule.trend,
        "interpretation": rule.interpretation,
        "action": rule.action,
        "matched_rule_id": rule.id,
        "rule_origin": (
            "generated_fallback" if generated_fallback else
            "custom" if rule.score_mode == "custom" else "system_template"
        ),
        "rules_user_id": rule.user_id,  # handig voor debug
    }


# ============================================================
# Scoring (category: many indicators)
# ============================================================
def score_category(
    conn,
    user_id: int,
    category: str,
    indicator_values: Dict[str, Any],
    persist: bool = True,
    ts: Optional[datetime] = None,
    symbol: str = "BTC"
) -> Dict[str, Any]:
    if ts is None:
        ts = datetime.utcnow()

    if not isinstance(indicator_values, dict):
        indicator_values = {}

    items: List[Dict[str, Any]] = []
    weighted_sum = 0.0
    raw_sum = 0.0
    total_weight = 0.0
    count = 0

    for indicator, value in indicator_values.items():
        if not indicator:
            continue

        scored = score_indicator(
            conn,
            category=category,
            indicator=str(indicator),
            value=value,
            user_id=user_id,  # ✅ user-based override
        )
        if scored.get("score") is None:
            continue
        items.append(scored)

        s = float(scored["score"])
        w = float(scored["weight"] or 1.0)

        weighted_sum += s * w
        raw_sum += s
        total_weight += w
        count += 1

    raw_avg = (raw_sum / count) if count > 0 else None
    weighted_avg = (weighted_sum / total_weight) if total_weight > 0 else None

    raw_avg_i = _clamp_score(int(round(raw_avg))) if raw_avg is not None else None
    weighted_avg_i = _clamp_score(int(round(weighted_avg))) if weighted_avg is not None else None

    if persist and count > 0:
        persist_indicator_scores(
            conn=conn,
            user_id=user_id,
            category=category,
            items=items,
            ts=ts,
            symbol=symbol
        )

    return {
        "category": category,
        "timestamp": ts.isoformat(),
        "items": items,
        "raw_avg_score": raw_avg_i,
        "weighted_score": weighted_avg_i,
        "total_weight": float(total_weight),
    }


# ============================================================
# Persist to *_indicator_scores
# ============================================================
def persist_indicator_scores(
    conn,
    user_id: int,
    category: str,
    items: List[Dict[str, Any]],
    ts: Optional[datetime] = None,
    symbol: str = "BTC"
) -> None:
    if ts is None:
        ts = datetime.utcnow()

    with conn.cursor() as cur:
        for it in items:
            indicator_val = str(it.get("indicator") or "").strip()
            if not indicator_val:
                continue

            value = it.get("value")
            score = _to_int(it.get("score"))
            trend = it.get("trend")
            interpretation = it.get("interpretation")
            action = it.get("action")

            score = _clamp_score(int(score or 10))

            if category == "macro":
                cur.execute(
                    """
                    INSERT INTO macro_data (
                        name, value, score, trend, interpretation, action, timestamp, user_id, symbol
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (indicator_val, value, score, trend, interpretation, action, ts, user_id, symbol)
                )
            elif category == "market":
                cur.execute(
                    """
                    INSERT INTO market_data_indicators (
                        name, value, score, trend, interpretation, action, timestamp, user_id, symbol
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (indicator_val, value, score, trend, interpretation, action, ts, user_id, symbol)
                )
            elif category == "technical":
                cur.execute(
                    """
                    INSERT INTO technical_indicators (
                        indicator, value, score, advies, uitleg, timestamp, user_id, symbol
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (indicator_val, value, score, trend, interpretation, ts, user_id, symbol)
                )


# ============================================================
# Convenience: run scoring with its own DB connection
# ============================================================
def run_category_scoring(
    user_id: int,
    category: str,
    indicator_values: Dict[str, Any],
    persist: bool = True,
    ts: Optional[datetime] = None,
    symbol: str = "BTC"
) -> Dict[str, Any]:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("DB niet beschikbaar")

    try:
        result = score_category(
            conn=conn,
            user_id=user_id,
            category=category,
            indicator_values=indicator_values,
            persist=persist,
            ts=ts,
            symbol=symbol
        )
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        logger.exception("❌ run_category_scoring failed")
        raise
    finally:
        conn.close()
