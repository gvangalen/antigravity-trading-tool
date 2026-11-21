#!/usr/bin/env python3
"""Reproduce a legacy weekly-DCA check and verify its migration locally.

Every DDL and insert runs inside one rollback-only transaction. This refuses
all hosts except the disposable FINN PostgreSQL fixture.
"""
from __future__ import annotations

import os
import runpy
from pathlib import Path

from backend.utils.db import get_db_connection


MIGRATION = Path(__file__).resolve().parent / "migrations/2026_11_18_smart_dca_legacy_schedule_constraint.py"
LEGACY_CHECK = """
ALTER TABLE setups ADD CONSTRAINT dca_logic_check CHECK (
    setup_type IS DISTINCT FROM 'dca'
    OR dca_frequency = 'daily'
    OR (dca_frequency = 'weekly' AND dca_day IS NOT NULL)
    OR (dca_frequency = 'monthly' AND dca_month_day IS NOT NULL)
) NOT VALID
"""


def main() -> None:
    if (os.getenv("DB_HOST"), os.getenv("DB_PORT"), os.getenv("DB_NAME")) != (
        "127.0.0.1", os.getenv("FINN_LOCAL_POSTGRES_PORT", "55432"), "finn_local"
    ):
        raise RuntimeError("smart_dca_constraint_probe_requires_disposable_local_db")
    connection = get_db_connection()
    if connection is None:
        raise RuntimeError("smart_dca_constraint_probe_db_unavailable")
    sql = runpy.run_path(str(MIGRATION))["SQL"]
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '15s'")
            cursor.execute("ALTER TABLE setups DROP CONSTRAINT IF EXISTS setups_smart_dca_schedule_valid")
            cursor.execute("ALTER TABLE setups DROP CONSTRAINT IF EXISTS dca_logic_check")
            cursor.execute(LEGACY_CHECK)

            def accepted(*, trigger: str, frequency: str | None, day: str | None = None,
                         setup_type: str = "dca") -> bool:
                cursor.execute("SAVEPOINT trial")
                try:
                    cursor.execute(
                        """INSERT INTO setups
                           (name, symbol, timeframe, setup_type, dca_frequency,
                            dca_trigger_mode, dca_day)
                           VALUES ('Smart DCA migration probe', 'BTC', '1D', %s, %s, %s, %s)""",
                        (setup_type, frequency, trigger, day),
                    )
                except Exception as error:
                    if getattr(error, "pgcode", None) != "23514":
                        raise
                    cursor.execute("ROLLBACK TO SAVEPOINT trial")
                    return False
                cursor.execute("ROLLBACK TO SAVEPOINT trial")
                return True

            assert not accepted(trigger="benchmark", frequency="weekly")
            cursor.execute(sql)
            assert accepted(trigger="benchmark", frequency="weekly")
            assert accepted(trigger="calendar", frequency="weekly", day="friday")
            assert not accepted(trigger="calendar", frequency="weekly")
            assert not accepted(trigger="benchmark", frequency="weekly", day="friday")
            assert not accepted(trigger="benchmark", frequency=None)
            assert accepted(trigger="calendar", frequency=None, setup_type="trade")
            cursor.execute("SELECT pg_get_expr(conbin, conrelid) FROM pg_constraint "
                           "WHERE conrelid = 'setups'::regclass AND conname = 'dca_logic_check'")
            first_definition = cursor.fetchone()[0]
            cursor.execute(sql)
            cursor.execute("SELECT pg_get_expr(conbin, conrelid) FROM pg_constraint "
                           "WHERE conrelid = 'setups'::regclass AND conname = 'dca_logic_check'")
            assert cursor.fetchone()[0] == first_definition
        print("smart_dca_schedule_migration: legacy rejection, benchmark insert, calendar guard and replay passed")
    finally:
        connection.rollback()
        connection.close()


if __name__ == "__main__":
    main()
