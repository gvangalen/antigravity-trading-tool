"""Report whether the one-time Paper exit migration needs writer quiescence."""

from backend.utils.db import get_db_connection


def main() -> None:
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("paper_exit_migration_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM pg_constraint c
                    WHERE c.conrelid='bot_decisions'::regclass
                      AND c.contype='u'
                      AND pg_get_constraintdef(c.oid)=
                          'UNIQUE (user_id, bot_id, decision_date)'
                ), EXISTS (
                    SELECT 1 FROM pg_index x
                    JOIN pg_class i ON i.oid=x.indexrelid
                    WHERE x.indrelid='bot_decisions'::regclass
                      AND x.indisunique AND x.indpred IS NULL
                      AND pg_get_indexdef(i.oid) LIKE
                          '%(user_id, bot_id, decision_date)%'
                ), EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='bot_decisions' AND column_name='decision_kind'
                )
            """)
            old_constraint, old_index, kind_exists = cur.fetchone()
        print("legacy" if old_constraint or old_index or not kind_exists else "current")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
