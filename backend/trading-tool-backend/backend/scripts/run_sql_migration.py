"""Run a single SQL migration module against the configured PostgreSQL database.

Usage:
    python3 backend/scripts/run_sql_migration.py backend/scripts/migrations/2026_05_24_platform_hardening_phase1.py
"""

from __future__ import annotations

import argparse
import logging
import runpy
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.utils.db import get_db_connection


logger = logging.getLogger(__name__)


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
        with conn:
            with conn.cursor() as cur:
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
