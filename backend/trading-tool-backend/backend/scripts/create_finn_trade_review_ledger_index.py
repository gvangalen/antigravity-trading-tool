"""Build the review cursor index without blocking bot_ledger writes.

Run before the transactional 2026_10_16_finn_trade_reviews migration. A failed
CREATE INDEX CONCURRENTLY can leave an invalid index, which this preflight
removes before retrying. Never run it through run_sql_migration.py.
"""

from backend.scripts.run_sql_migration import _timeout_setting
from backend.utils.db import get_db_connection


INDEX = "ix_finn_trade_review_ledger_user_cursor"


def run() -> None:
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("Could not connect to database")
    try:
        conn.autocommit = True  # CREATE/DROP INDEX CONCURRENTLY require this.
        with conn.cursor() as cur:
            cur.execute("SET lock_timeout = %s", (_timeout_setting("TRADAMIND_MIGRATION_LOCK_TIMEOUT_MS", 15_000),))
            cur.execute("SET statement_timeout = %s", (_timeout_setting("TRADAMIND_MIGRATION_STATEMENT_TIMEOUT_MS", 120_000),))
            cur.execute("""
                SELECT i.indisvalid, t.relname
                FROM pg_index i
                JOIN pg_class idx ON idx.oid = i.indexrelid
                JOIN pg_class t ON t.oid = i.indrelid
                WHERE i.indexrelid = to_regclass(%s)
            """, (INDEX,))
            existing = cur.fetchone()
            if existing and existing[1] != "bot_ledger":
                raise RuntimeError("Review index name belongs to another table")
            if existing and not existing[0]:
                cur.execute(f"DROP INDEX CONCURRENTLY {INDEX}")
            cur.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX}
                ON bot_ledger (user_id, id) WHERE entry_type='execute'
            """)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
