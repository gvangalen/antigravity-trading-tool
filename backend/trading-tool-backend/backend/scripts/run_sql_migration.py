"""Run a single SQL migration module against the configured PostgreSQL database.

Usage:
    python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_platform_hardening_phase1.py
"""

from __future__ import annotations

import argparse
import logging
import os
import runpy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.db import get_db_connection


logger = logging.getLogger(__name__)


def _timeout_setting(name: str, default_ms: int) -> str:
    """Return a validated PostgreSQL timeout value for one migration session."""
    raw_value = os.getenv(name, str(default_ms))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer in milliseconds") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer in milliseconds")
    return f"{value}ms"


def run_migration(path: str) -> None:
    migration_path = Path(path)
    if not migration_path.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_path}")

    namespace = runpy.run_path(str(migration_path))
    sql = namespace.get("SQL")
    if not sql or not isinstance(sql, str):
        raise ValueError(f"Migration {migration_path} does not expose a SQL string")

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("Could not connect to database")

    try:
        lock_timeout = _timeout_setting("TRADAMIND_MIGRATION_LOCK_TIMEOUT_MS", 15_000)
        statement_timeout = _timeout_setting("TRADAMIND_MIGRATION_STATEMENT_TIMEOUT_MS", 120_000)
        logger.info(
            "Applying migration %s with lock_timeout=%s statement_timeout=%s",
            migration_path,
            lock_timeout,
            statement_timeout,
        )
        with conn:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = %s", (lock_timeout,))
                cur.execute("SET LOCAL statement_timeout = %s", (statement_timeout,))
                cur.execute(sql)
        logger.info("✅ Migration applied: %s", migration_path)
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one SQL migration file.")
    parser.add_argument("migration", help="Path to migration .py file exposing SQL")
    args = parser.parse_args()
    run_migration(args.migration)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    main()
