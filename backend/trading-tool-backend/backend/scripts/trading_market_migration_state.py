"""Report the exact-market score/config uniqueness cutover state."""

from backend.utils.db import get_db_connection


def main() -> None:
    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("trading_market_migration_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT to_regclass('trading_markets') IS NOT NULL,
                       to_regclass('ux_daily_scores_legacy_market_scope') IS NOT NULL,
                       to_regclass('ux_daily_scores_exact_market_scope') IS NOT NULL,
                       to_regclass('ux_indicator_configs_legacy_market_scope') IS NOT NULL,
                       to_regclass('ux_indicator_configs_exact_market_scope') IS NOT NULL,
                       EXISTS (
                           SELECT 1 FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid
                           WHERE x.indrelid='daily_scores'::regclass
                             AND x.indisunique AND x.indpred IS NULL
                             AND pg_get_indexdef(i.oid) LIKE
                                 '%(user_id, symbol, report_date)%'
                       ),
                       EXISTS (
                           SELECT 1 FROM pg_index x JOIN pg_class i ON i.oid=x.indexrelid
                           WHERE x.indrelid='user_indicator_configs'::regclass
                             AND x.indisunique
                             AND pg_get_indexdef(i.oid) LIKE
                                 '%(user_id, symbol, category, indicator)%'
                             AND (x.indpred IS NULL OR
                                  pg_get_expr(x.indpred, x.indrelid) NOT LIKE '%market_id%')
                       )
            """)
            (market_table, legacy_score_index, exact_score_index,
             legacy_config_index, exact_config_index, old_scores, old_configs) = cur.fetchone()
        if not all((market_table, legacy_score_index, exact_score_index,
                    legacy_config_index, exact_config_index)):
            print("legacy")
        elif old_scores or old_configs:
            print("expanded")
        else:
            print("current")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
