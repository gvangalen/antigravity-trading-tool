"""Remove base-only uniqueness after every old score/config writer has stopped.

The expand migration installs partial legacy and exact-market arbiters first.
This cutover allows one owner to keep BTC/EUR and BTC/USDT evidence on the
same date without changing the legacy BTC score row.
"""

SQL = """
DO $$
BEGIN
    IF to_regclass('ux_daily_scores_legacy_market_scope') IS NULL
       OR to_regclass('ux_daily_scores_exact_market_scope') IS NULL
       OR to_regclass('ux_indicator_configs_legacy_market_scope') IS NULL
       OR to_regclass('ux_indicator_configs_exact_market_scope') IS NULL THEN
        RAISE EXCEPTION 'trading_market_identity_expand_required';
    END IF;
END $$;

DO $$
DECLARE old_constraint RECORD;
BEGIN
    FOR old_constraint IN
        SELECT c.conname, c.conrelid::regclass AS table_name
        FROM pg_constraint c
        WHERE c.contype='u'
          AND c.conrelid IN ('daily_scores'::regclass,
                            'user_indicator_configs'::regclass)
          AND (
            (c.conrelid='daily_scores'::regclass AND
             pg_get_constraintdef(c.oid)='UNIQUE (user_id, symbol, report_date)')
            OR
            (c.conrelid='user_indicator_configs'::regclass AND
             pg_get_constraintdef(c.oid)='UNIQUE (user_id, symbol, category, indicator)')
          )
    LOOP
        EXECUTE format('ALTER TABLE %s DROP CONSTRAINT %I',
                       old_constraint.table_name, old_constraint.conname);
    END LOOP;
END $$;

DO $$
DECLARE old_index RECORD;
BEGIN
    FOR old_index IN
        SELECT n.nspname, i.relname
        FROM pg_index x
        JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=i.relnamespace
        WHERE x.indrelid IN ('daily_scores'::regclass,
                             'user_indicator_configs'::regclass)
          AND x.indisunique
          AND (
            (x.indrelid='daily_scores'::regclass AND x.indpred IS NULL AND
             pg_get_indexdef(i.oid) LIKE '%(user_id, symbol, report_date)%')
            OR
            (x.indrelid='user_indicator_configs'::regclass AND
             pg_get_indexdef(i.oid) LIKE '%(user_id, symbol, category, indicator)%' AND
             (x.indpred IS NULL OR
              pg_get_expr(x.indpred, x.indrelid) NOT LIKE '%market_id%'))
          )
          AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid=i.oid)
    LOOP
        EXECUTE format('DROP INDEX %I.%I', old_index.nspname, old_index.relname);
    END LOOP;
END $$;
"""
