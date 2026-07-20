import logging
import json
import hashlib
from datetime import date
from typing import Any, Dict, Optional

from celery import shared_task

from backend.utils.db import get_db_connection
from backend.services.ai_usage_observability_service import ai_usage_context, log_background_ai_skip
from backend.ai_agents.strategy_ai_agent import (
    generate_strategy_from_setup,
    analyze_strategies,
    adjust_strategy_for_today,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


# ============================================================
# 🔧 Helpers
# ============================================================
def safe_json(value: Any) -> Dict[str, Any]:
    """Zorgt dat 'data' altijd een dict is."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def stable_input_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(convert_decimals(payload), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def input_is_unchanged(previous_hash: Optional[str], current_hash: str) -> bool:
    return bool(previous_hash) and previous_hash == current_hash


def existing_strategy_snapshot_hash(conn, *, user_id: int, setup_id: int, snapshot_date: date) -> Optional[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT changes
            FROM active_strategy_snapshot
            WHERE user_id = %s AND setup_id = %s AND snapshot_date <= %s
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
            """,
            (user_id, setup_id, snapshot_date),
        )
        row = cur.fetchone()
    changes = safe_json(row[0]) if row else {}
    value = changes.get("input_hash")
    return str(value) if value else None


def reuse_strategy_snapshot(
    conn,
    *,
    user_id: int,
    setup_id: int,
    symbol: str,
    snapshot_date: date,
    input_hash: str,
) -> None:
    """Carry the latest identical result forward without invoking the model."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO active_strategy_snapshot (
                user_id, strategy_id, setup_id, entry, stop_loss, targets,
                confidence_score, adjustment_reason, market_context, changes, snapshot_date
            )
            SELECT user_id, strategy_id, setup_id, entry, stop_loss, targets,
                   confidence_score, adjustment_reason, market_context, changes, %s
            FROM active_strategy_snapshot
            WHERE user_id = %s AND setup_id = %s AND snapshot_date <= %s
            ORDER BY snapshot_date DESC, created_at DESC
            LIMIT 1
            ON CONFLICT (user_id, setup_id, snapshot_date)
            DO UPDATE SET
                strategy_id = EXCLUDED.strategy_id,
                entry = EXCLUDED.entry,
                stop_loss = EXCLUDED.stop_loss,
                targets = EXCLUDED.targets,
                confidence_score = EXCLUDED.confidence_score,
                adjustment_reason = EXCLUDED.adjustment_reason,
                market_context = EXCLUDED.market_context,
                changes = EXCLUDED.changes,
                created_at = NOW()
            """,
            (snapshot_date, user_id, setup_id, snapshot_date),
        )
        cur.execute(
            """
            INSERT INTO ai_category_insights (
                user_id, category, symbol, avg_score, trend, bias, risk,
                summary, top_signals, date, created_at
            )
            SELECT user_id, category, %s, avg_score, trend, bias, risk,
                   summary, %s::jsonb, %s, NOW()
            FROM ai_category_insights
            WHERE user_id = %s
              AND category = 'strategy'
              AND symbol = %s
              AND top_signals @> %s::jsonb
            ORDER BY date DESC, created_at DESC
            LIMIT 1
            ON CONFLICT (user_id, category, symbol, date)
            DO UPDATE SET
                summary = EXCLUDED.summary,
                top_signals = EXCLUDED.top_signals,
                created_at = NOW()
            """,
            (
                symbol,
                json.dumps([f"input_hash:{input_hash}"]),
                snapshot_date,
                user_id,
                symbol,
                json.dumps([f"input_hash:{input_hash}"]),
            ),
        )

def convert_decimals(obj):
    from decimal import Decimal

    if isinstance(obj, list):
        return [convert_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    return obj


def safe_numeric(value: Any) -> Optional[float]:
    """
    Probeert AI-output om te zetten naar numeric voor DB.
    Accepteert:
    - 42500
    - 42500.5
    - "42500"
    - "42,500"
    - "42500 - 43000" (pakt eerste getal)
    Alles anders -> None
    """
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, str):
        try:
            s = value.strip().replace(",", ".")
            s = s.split()[0]
            s = s.split("-")[0]
            s = s.replace("..", ".")
            return float(s)
        except Exception:
            return None

    return None


def safe_confidence(value: Any, fallback: int = 50) -> float:
    try:
        v = float(value)
        if v < 0:
            return 0.0
        if v > 100:
            return 100.0
        return v
    except Exception:
        return float(fallback)


def _get_strategy_columns(conn) -> set:
    """Check welke kolommen bestaan in de strategies tabel (schema-proof)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name='strategies';
            """
        )
        return {r[0] for r in cur.fetchall()}


# ============================================================
# 🔹 Load setup (STRICT volgens DB schema)
# ============================================================
def load_setup_from_db(setup_id: int, user_id: int) -> dict:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Geen databaseverbinding")

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    name,
                    symbol,
                    timeframe,
                    setup_type,
                    description,
                    filters
                FROM setups
                WHERE id = %s AND user_id = %s
                LIMIT 1;
                """,
                (setup_id, user_id),
            )

            row = cur.fetchone()
            if not row:
                raise ValueError("Setup niet gevonden")

            return {
                "id": row[0],
                "name": row[1],
                "symbol": row[2],
                "timeframe": row[3],
                "setup_type": row[4],  # ✅ NIEUW
                "description": row[5],
                "filters": row[6],
            }
    finally:
        conn.close()


# ============================================================
# 🔹 Load LAATSTE strategy voor setup (schema-proof)
# ============================================================
def load_latest_strategy(setup_id: int, user_id: int) -> Optional[dict]:
    conn = get_db_connection()
    if not conn:
        return None

    try:
        cols = _get_strategy_columns(conn)

        select_fields = [
            "id",
            "entry",
            "targets",
            "stop_loss",
            "explanation",
            "data",
            "created_at",
        ]

        if "risk_reward" in cols:
            select_fields.insert(4, "risk_reward")

        query = f"""
            SELECT {", ".join(select_fields)}
            FROM strategies
            WHERE setup_id = %s AND user_id = %s
            ORDER BY created_at DESC
            LIMIT 1;
        """

        with conn.cursor() as cur:
            cur.execute(query, (setup_id, user_id))
            row = cur.fetchone()

        if not row:
            return None

        row_map = dict(zip(select_fields, row))
        targets = row_map.get("targets") or []

        result = {
            "strategy_id": row_map.get("id"),
            "entry": float(row_map["entry"]) if row_map.get("entry") is not None else None,
            "targets": [float(t) for t in targets],
            "stop_loss": float(row_map["stop_loss"]) if row_map.get("stop_loss") is not None else None,
            "explanation": row_map.get("explanation"),
            "data": safe_json(row_map.get("data")),
            "created_at": row_map.get("created_at").isoformat()
            if row_map.get("created_at")
            else None,
        }

        if "risk_reward" in row_map:
            result["risk_reward"] = row_map.get("risk_reward")

        return result

    finally:
        conn.close()


# ============================================================
# 🚀 INITIËLE STRATEGY GENERATIE
# ============================================================
@shared_task(name="backend.celery_task.strategy_task.generate_for_setup")
def generate_for_setup(user_id: int, setup_id: int):

    logger.info("🚀 Strategy generatie | user=%s setup=%s", user_id, setup_id)
    conn = None

    try:
        setup = load_setup_from_db(setup_id, user_id)
        strategy = generate_strategy_from_setup(setup)

        conn = get_db_connection()
        if not conn:
            raise RuntimeError("Geen databaseverbinding")

        cols = _get_strategy_columns(conn)
        has_risk_reward = "risk_reward" in cols

        # 🔥 FIX: base_amount toegevoegd
        insert_cols = [
            "setup_id",
            "entry",
            "targets",
            "stop_loss",
            "explanation",
            "base_amount",   # ✅ FIX
            "data",
            "user_id",
        ]

        if has_risk_reward:
            insert_cols.insert(5, "risk_reward")

        placeholders = ", ".join(["%s"] * len(insert_cols))

        targets = strategy.get("targets") or []
        targets = [safe_numeric(t) for t in targets if safe_numeric(t) is not None]

        # 🔥 FIX: base_amount altijd vullen
        base_amount = safe_numeric(strategy.get("base_amount")) or 50

        enriched_data = {
            **strategy,
            "setup_type": setup.get("setup_type"),
        }

        values = [
            setup_id,
            safe_numeric(strategy.get("entry")),
            targets,
            safe_numeric(strategy.get("stop_loss")),
            strategy.get("explanation"),
        ]

        if has_risk_reward:
            values.append(strategy.get("risk_reward"))

        # 🔥 base_amount op juiste plek
        values.append(base_amount)

        values.extend([
            json.dumps(enriched_data),
            user_id,
        ])

        with conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO strategies ({", ".join(insert_cols)})
                VALUES ({placeholders})
                RETURNING id;
                """,
                tuple(values),
            )
            strategy_id = cur.fetchone()[0]
            conn.commit()

        logger.info(
            "✅ Strategy opgeslagen (id=%s, base_amount=%s)",
            strategy_id,
            base_amount
        )

        return {
            "success": True,
            "strategy_id": strategy_id,
        }

    except Exception:
        logger.error("❌ Strategy generatie fout", exc_info=True)

        if conn:
            try:
                conn.rollback()
            except Exception:
                pass

        return {"success": False}

    finally:
        if conn:
            conn.close()
# ============================================================
# 🧠 ANALYSE BESTAANDE STRATEGY (AI)
# ============================================================
@shared_task(name="backend.celery_task.strategy_task.analyze_strategy")
def analyze_strategy(user_id: int, strategy_id: int):

    logger.info("🧠 Analyse strategy | user=%s strategy=%s", user_id, strategy_id)

    conn = get_db_connection()
    if not conn:
        raise RuntimeError("Geen databaseverbinding")

    def convert_decimals(obj):
        from decimal import Decimal

        if isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, Decimal):
            return float(obj)
        return obj

    try:
        cols = _get_strategy_columns(conn)

        select_fields = [
            "id",
            "setup_id",
            "entry",
            "targets",
            "stop_loss",
            "explanation",
            "data",
            "created_at",
        ]

        if "risk_reward" in cols:
            select_fields.insert(5, "risk_reward")

        query = f"""
            SELECT {", ".join(select_fields)}
            FROM strategies
            WHERE id = %s AND user_id = %s;
        """

        with conn.cursor() as cur:
            cur.execute(query, (strategy_id, user_id))
            row = cur.fetchone()

        if not row:
            raise ValueError("Strategy niet gevonden")

        row_map = dict(zip(select_fields, row))

        # 🔥 CRUCIALE FIX → ALLES NUMERIC MAKEN VOOR JSON
        payload = [
            {
                "strategy_id": row_map["id"],
                "setup_id": row_map["setup_id"],
                "entry": safe_numeric(row_map["entry"]),
                "targets": [
                    safe_numeric(t) for t in (row_map.get("targets") or [])
                ],
                "stop_loss": safe_numeric(row_map["stop_loss"]),
                "risk_reward": safe_numeric(row_map.get("risk_reward")),
                "explanation": row_map["explanation"],
                "data": convert_decimals(safe_json(row_map["data"])),
                "created_at": row_map["created_at"].isoformat()
                if row_map["created_at"] else None,
            }
        ]

        # 🔥 EXTRA SAFETY (voor nested Decimal)
        payload = convert_decimals(payload)

        with ai_usage_context(
            user_id=user_id,
            symbol="BTC",
            request_source="background_job",
            run_kind="scheduled",
            entry_point="celery_task.strategy_task:analyze_strategy",
            caller_tag="celery_task.strategy_task:analyze_strategy",
            job_name="analyze_strategy",
            job_id=getattr(getattr(analyze_strategy, "request", None), "id", None),
        ):
            analysis = analyze_strategies(
                user_id=user_id,
                strategies=payload,
            )

        if not analysis:
            raise RuntimeError("AI analyse gaf None terug")

        # 🔥 FIX → Decimal uit AI response halen
        analysis = convert_decimals(analysis)

        explanation_text = (
            f"{analysis.get('comment', '')}\n\n"
            f"{analysis.get('recommendation', '')}"
        ).strip()

        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE strategies
                SET data = jsonb_set(
                    COALESCE(data,'{}'::jsonb),
                    '{ai_explanation}',
                    %s::jsonb,
                    true
                )
                WHERE id = %s AND user_id = %s;
                """,
                (json.dumps(explanation_text), strategy_id, user_id),
            )

        conn.commit()

        logger.info("✅ Strategy AI explanation opgeslagen")

        return {"success": True}

    except Exception:
        logger.exception("❌ analyze_strategy crash")
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# 🧠 Run DCA-Strategy Snapshot
# ============================================================
def run_dca_strategy_snapshot(user_id: int, setup: dict):
    logger.info("🟢 DCA snapshot gestart | user=%s setup=%s", user_id, setup["id"])

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen databaseverbinding")
        return

    today = date.today()

    try:
        # 1️⃣ Scores ophalen
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT macro_score, technical_score, market_score
                FROM daily_scores
                WHERE user_id = %s
                  AND report_date = CURRENT_DATE
                LIMIT 1;
                """,
                (user_id,),
            )
            scores = cur.fetchone()

        if not scores:
            logger.warning("⚠️ Geen daily_scores gevonden")
            return

        def material_score(value):
            if value is None:
                return None
            return round(float(value) / 5) * 5

        market_context = {
            "macro_score": material_score(scores[0]),
            "technical_score": material_score(scores[1]),
            "market_score": material_score(scores[2]),
        }

        base_strategy = load_latest_strategy(setup["id"], user_id)
        if not base_strategy:
            logger.warning("⚠️ Geen base strategy gevonden")
            return

        adjustment = adjust_strategy_for_today(
            user_id=user_id,
            base_strategy=base_strategy,
            setup=setup,
            market_context=market_context,
        )

        if not adjustment:
            logger.warning("⚠️ Geen AI adjustment")
            return

        confidence = safe_confidence(
            adjustment.get("confidence_score"),
            fallback=50,
        )

        # ❌ strategy_type eruit
        # ✅ setup_type erin
        analysis = analyze_strategies(
            user_id=user_id,
            strategies=[
                {
                    "strategy_id": base_strategy["strategy_id"],
                    "setup_id": setup["id"],
                    "setup_type": setup.get("setup_type"),  # 🔥 FIX
                    "confidence_score": confidence,
                    "market_context": market_context,
                    "adjustment_reason": adjustment.get("adjustment_reason"),
                }
            ],
        )

        if not analysis:
            logger.warning("⚠️ Geen AI analyse")
            return

        with conn.cursor() as cur:
            entry = safe_numeric(base_strategy.get("entry"))
            stop = safe_numeric(base_strategy.get("stop_loss"))
            targets = base_strategy.get("targets") or []
            targets_text = json.dumps(targets) if targets else None

            cur.execute(
                """
                INSERT INTO active_strategy_snapshot (
                    user_id,
                    strategy_id,
                    setup_id,
                    entry,
                    stop_loss,
                    targets,
                    confidence_score,
                    adjustment_reason,
                    market_context,
                    changes,
                    snapshot_date
                )
                VALUES (
                    %s, %s, %s,
                    %s, %s,
                    %s,
                    %s,
                    %s,
                    %s::jsonb,
                    %s::jsonb,
                    %s
                )
                ON CONFLICT (user_id, setup_id, snapshot_date)
                DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    entry = EXCLUDED.entry,
                    stop_loss = EXCLUDED.stop_loss,
                    targets = EXCLUDED.targets,
                    confidence_score = EXCLUDED.confidence_score,
                    adjustment_reason = EXCLUDED.adjustment_reason,
                    market_context = EXCLUDED.market_context,
                    changes = EXCLUDED.changes,
                    created_at = NOW();
                """,
                (
                    user_id,
                    base_strategy["strategy_id"],
                    setup["id"],
                    entry,
                    stop,
                    targets_text,
                    confidence,
                    adjustment.get("adjustment_reason"),
                    json.dumps(market_context),
                    json.dumps(adjustment),
                    today,
                ),
            )

        conn.commit()
        logger.info("✅ DCA snapshot opgeslagen")

    except Exception:
        logger.error("❌ DCA snapshot fout", exc_info=True)
        try:
            conn.rollback()
        except Exception:
            pass
    finally:
        conn.close()


# ============================================================
# 🟡 DAGELIJKSE STRATEGY INSIGHT
# ============================================================
def update_strategy_insight(user_id: int, analysis: dict, symbol: str = "BTC"):
    conn = get_db_connection()
    if not conn:
        return

    try:
        summary = (
            f"{analysis.get('comment', '')}\n\n"
            f"{analysis.get('recommendation', '')}"
        ).strip()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights (
                    user_id,
                    category,
                    symbol,
                    avg_score,
                    trend,
                    bias,
                    risk,
                    summary,
                    top_signals,
                    date,
                    created_at
                )
                VALUES (
                    %s,
                    'strategy',
                    %s,
                    NULL,
                    'actief',
                    'plan actief',
                    'gemiddeld',
                    %s,
                    %s,
                    CURRENT_DATE,
                    NOW()
                )
                ON CONFLICT (user_id, category, symbol, date)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    created_at = NOW();
            """, (
                user_id,
                str(symbol or "BTC").upper(),
                summary,
                json.dumps([]),
            ))

        conn.commit()
        logger.info("✅ Strategy insight opgeslagen")

    finally:
        conn.close()

# ============================================================
# 🟡 DAGELIJKSE STRATEGY SNAPSHOT + DASHBOARD INSIGHT
# ============================================================
@shared_task(name="backend.celery_task.strategy_task.run_daily_strategy_snapshot")
def run_daily_strategy_snapshot(user_id: int):

    logger.info("🟡 Daily strategy snapshot | user=%s", user_id)
    today = date.today()

    conn = get_db_connection()
    if not conn:
        logger.error("❌ Geen databaseverbinding")
        return

    def convert_decimals(obj):
        from decimal import Decimal
        if isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, Decimal):
            return float(obj)
        return obj

    try:
        # =====================================================
        # 1️⃣ BEST SETUP
        # =====================================================
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT setup_id
                FROM daily_setup_scores
                WHERE user_id = %s
                  AND report_date = %s
                  AND is_best = TRUE
                LIMIT 1;
                """,
                (user_id, today),
            )
            row = cur.fetchone()

        if not row:
            logger.warning("⚠️ Geen best-of-day setup")
            return

        setup_id = row[0]
        setup = load_setup_from_db(setup_id, user_id)
        setup_symbol = str(setup.get("symbol") or "BTC").upper()

        # =====================================================
        # 2️⃣ STRATEGY
        # =====================================================
        base_strategy = load_latest_strategy(setup_id, user_id)
        setup_type = (setup.get("setup_type") or "").lower()

        needs_bootstrap = (
            setup_type != "dca" and (
                not base_strategy
                or base_strategy.get("entry") is None
                or base_strategy.get("stop_loss") is None
                or not base_strategy.get("targets")
            )
        )

        if needs_bootstrap:
            logger.warning("⚠️ Strategy ontbreekt → bootstrap")

            strategy = generate_strategy_from_setup(setup)

            entry = safe_numeric(strategy.get("entry"))
            stop = safe_numeric(strategy.get("stop_loss"))
            targets = [
                safe_numeric(t)
                for t in strategy.get("targets") or []
                if safe_numeric(t) is not None
            ]

            base_amount = safe_numeric(strategy.get("base_amount"))
            if base_amount is None:
                raise RuntimeError("base_amount ontbreekt")

            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO strategies (
                        setup_id, entry, targets, stop_loss,
                        explanation, setup_type, base_amount, data, user_id
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                    """,
                    (
                        setup_id,
                        entry,
                        targets,
                        stop,
                        strategy.get("explanation"),
                        setup_type,
                        base_amount,
                        json.dumps(strategy),
                        user_id,
                    ),
                )
                strategy_id = cur.fetchone()[0]

            conn.commit()

            base_strategy = {
                "strategy_id": strategy_id,
                "entry": entry,
                "stop_loss": stop,
                "targets": targets,
            }

        # =====================================================
        # 3️⃣ MARKET CONTEXT
        # =====================================================
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT macro_score, technical_score, market_score
                FROM daily_scores
                WHERE user_id = %s
                  AND report_date = %s
                  AND symbol = %s
                LIMIT 1;
                """,
                (user_id, today, setup_symbol),
            )
            scores = cur.fetchone()

        if not scores:
            return

        market_context = {
            "macro_score": float(scores[0]) if scores[0] is not None else None,
            "technical_score": float(scores[1]) if scores[1] is not None else None,
            "market_score": float(scores[2]) if scores[2] is not None else None,
        }

        analysis_input = {
            "setup": {
                "id": setup_id,
                "symbol": setup_symbol,
                "timeframe": setup.get("timeframe"),
                "setup_type": setup_type,
                "filters": setup.get("filters"),
            },
            "strategy": {
                "id": base_strategy["strategy_id"],
                "entry": base_strategy.get("entry"),
                "targets": base_strategy.get("targets") or [],
                "stop_loss": base_strategy.get("stop_loss"),
            },
            "market_context": market_context,
        }
        input_hash = stable_input_hash(analysis_input)
        previous_input_hash = existing_strategy_snapshot_hash(
            conn,
            user_id=user_id,
            setup_id=setup_id,
            snapshot_date=today,
        )
        if input_is_unchanged(previous_input_hash, input_hash):
            logger.info("♻️ Strategy AI overgeslagen: input onveranderd | user=%s setup=%s", user_id, setup_id)
            reuse_strategy_snapshot(
                conn,
                user_id=user_id,
                setup_id=setup_id,
                symbol=setup_symbol,
                snapshot_date=today,
                input_hash=input_hash,
            )
            conn.commit()
            log_background_ai_skip(
                user_id=user_id,
                symbol=setup_symbol,
                purpose="strategy_snapshot_analysis",
                entry_point="celery_task.strategy_task:run_daily_strategy_snapshot",
            )
            return {"skipped": True, "reason": "input_unchanged", "input_hash": input_hash}

        # =====================================================
        # 4️⃣ AI ANALYSE
        # =====================================================
        with ai_usage_context(
            user_id=user_id,
            symbol=setup_symbol,
            request_source="background_job",
            run_kind="scheduled",
            entry_point="celery_task.strategy_task:run_daily_strategy_snapshot",
            caller_tag="celery_task.strategy_task:run_daily_strategy_snapshot",
            job_name="run_daily_strategy_snapshot",
            job_id=getattr(getattr(run_daily_strategy_snapshot, "request", None), "id", None),
        ):
            analysis = analyze_strategies(
                user_id=user_id,
                strategies=[{
                    "strategy_id": base_strategy["strategy_id"],
                    "setup_id": setup_id,
                    "setup_type": setup_type,
                    "entry": base_strategy.get("entry"),
                    "targets": base_strategy.get("targets"),
                    "stop_loss": base_strategy.get("stop_loss"),
                    "market_context": market_context,
                }],
            )

        if not analysis:
            raise RuntimeError("AI analyse failed")

        analysis = convert_decimals(analysis)
        analysis["input_hash"] = input_hash

        # Reuse the same response for the strategy explanation. This avoids a
        # second model call for content already present in the snapshot result.
        explanation_text = (
            f"{analysis.get('comment', '')}\n\n"
            f"{analysis.get('recommendation', '')}"
        ).strip()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE strategies
                SET data = jsonb_set(
                    COALESCE(data, '{}'::jsonb),
                    '{ai_explanation}',
                    %s::jsonb,
                    true
                )
                WHERE id = %s AND user_id = %s
                """,
                (json.dumps(explanation_text), base_strategy["strategy_id"], user_id),
            )

        # =====================================================
        # 6️⃣ SNAPSHOT
        # =====================================================
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO active_strategy_snapshot (
                    user_id, strategy_id, setup_id,
                    entry, stop_loss, targets,
                    confidence_score, adjustment_reason,
                    market_context, changes, snapshot_date
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
                ON CONFLICT (user_id, setup_id, snapshot_date)
                DO UPDATE SET
                    strategy_id = EXCLUDED.strategy_id,
                    entry = EXCLUDED.entry,
                    stop_loss = EXCLUDED.stop_loss,
                    targets = EXCLUDED.targets,
                    confidence_score = EXCLUDED.confidence_score,
                    adjustment_reason = EXCLUDED.adjustment_reason,
                    market_context = EXCLUDED.market_context,
                    changes = EXCLUDED.changes,
                    created_at = NOW();
                """,
                (
                    user_id,
                    base_strategy["strategy_id"],
                    setup_id,
                    safe_numeric(base_strategy.get("entry")),
                    safe_numeric(base_strategy.get("stop_loss")),
                    json.dumps(base_strategy.get("targets") or []),
                    safe_confidence(analysis.get("confidence_score")),
                    analysis.get("recommendation"),
                    json.dumps(market_context),
                    json.dumps(analysis),
                    today,
                ),
            )

        conn.commit()

        logger.info("✅ Snapshot opgeslagen")

        # =====================================================
        # 🔥 FIX — LINKER CARD DIRECT UPDATEN
        # =====================================================
        summary = (
            f"{analysis.get('comment', '')}\n\n"
            f"{analysis.get('recommendation', '')}"
        ).strip()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO ai_category_insights (
                    user_id,
                    category,
                    symbol,
                    avg_score,
                    trend,
                    bias,
                    risk,
                    summary,
                    top_signals,
                    date,
                    created_at
                )
                VALUES (
                    %s,
                    'strategy',
                    %s,
                    NULL,
                    'actief',
                    'plan actief',
                    'gemiddeld',
                    %s,
                    %s,
                    CURRENT_DATE,
                    NOW()
                )
                ON CONFLICT (user_id, category, symbol, date)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    created_at = NOW();
            """, (
                user_id,
                setup_symbol,
                summary,
                json.dumps([f"input_hash:{input_hash}"]),
            ))

        conn.commit()

        logger.info("🧠 Strategy insight direct geüpdatet")

    except Exception:
        logger.exception("❌ Daily strategy snapshot crash")
        conn.rollback()
        raise

    finally:
        conn.close()

# ============================================================
# 🔄 BULK GENERATIE — BEWUST UIT
# ============================================================
@shared_task(name="backend.celery_task.strategy_task.generate_all")
def generate_all(user_id: int):
    return {
        "state": "IGNORED",
        "success": False,
        "reason": "Bulk AI strategie-generatie is uitgeschakeld",
    }


def debug_analyze_strategy(user_id: int, strategy_id: int):
    """
    Debug helper zonder Celery async gedrag.
    Roept de task-functie direct aan.
    """
    return analyze_strategy(user_id=user_id, strategy_id=strategy_id)
