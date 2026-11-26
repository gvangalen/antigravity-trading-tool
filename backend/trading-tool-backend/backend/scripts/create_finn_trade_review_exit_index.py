"""Build the bounded weekly owner-scan index without blocking review writes."""

from backend.scripts.run_sql_migration import _timeout_setting
from backend.utils.db import get_db_connection


INDEX = "ix_finn_trade_reviews_exit_user"


def run() -> None:
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("Could not connect to database")
    try:
        conn.autocommit = True
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
            if existing and existing[1] != "finn_trade_reviews":
                raise RuntimeError("Review exit index name belongs to another table")
            if existing and not existing[0]:
                cur.execute(f"DROP INDEX CONCURRENTLY {INDEX}")
            cur.execute(f"""
                CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX}
                ON finn_trade_reviews (exit_at, user_id)
            """)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
