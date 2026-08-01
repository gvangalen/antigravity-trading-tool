from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Sequence

from backend.utils.db import get_db_connection


logger = logging.getLogger(__name__)


def fetch_average_estimated_cost(
    *,
    model: str,
    purpose: Optional[str],
    entry_point: Optional[str],
) -> Optional[float]:
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(AVG(NULLIF(estimated_cost_if_full, 0)), AVG(NULLIF(cost, 0)), 0)
                FROM ai_usage_logs
                WHERE model = %s
                  AND purpose = %s
                  AND COALESCE(entry_point, '') = COALESCE(%s, '')
                  AND status IN ('full_ai', 'cache_exact', 'cache_semantic', 'fallback')
                  AND timestamp >= NOW() - interval '90 days'
                """,
                (model, purpose, entry_point),
            )
            row = cur.fetchone()
            if row and row[0]:
                return round(float(row[0]), 6)
    except Exception as exc:
        logger.warning("⚠️ Kon blocked cost estimate niet afleiden uit historie: %s", exc)
    finally:
        conn.close()
    return None


def fetch_supported_ai_usage_log_columns() -> Optional[set[str]]:
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'ai_usage_logs'
                """
            )
            rows = cur.fetchall()
            columns = {str(row[0]) for row in rows if row and row[0]}
            return columns or None
    except Exception as exc:
        logger.warning("⚠️ Kon ai_usage_logs schema niet inspecteren: %s", exc)
        return None
    finally:
        conn.close()


def insert_ai_usage_log_row(
    *,
    columns: Sequence[str],
    values: Dict[str, Any],
) -> None:
    conn = get_db_connection()
    if conn is None:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ai_usage_logs ("
                    + ", ".join(columns)
                    + ") VALUES ("
                    + ", ".join(["%s"] * len(columns))
                    + ")",
                    tuple(values[column] for column in columns),
                )
    finally:
        conn.close()


def fetch_user_email_snapshot(user_id: Optional[int]) -> Optional[str]:
    if not user_id:
        return None
    conn = get_db_connection()
    if conn is None:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email FROM users WHERE id = %s LIMIT 1", (user_id,))
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else None
    except Exception as exc:
        logger.warning("⚠️ Kon user email snapshot niet ophalen: %s", exc)
        return None
    finally:
        conn.close()
