"""Make persisted AI insights unambiguously asset scoped."""

SQL = """
ALTER TABLE ai_category_insights
ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';

UPDATE ai_category_insights
SET symbol = CASE
    WHEN category IN ('macro', 'market', 'technical') THEN 'GLOBAL'
    ELSE 'BTC'
END
WHERE symbol IS NULL OR BTRIM(symbol) = '' OR (
    symbol = 'BTC' AND category IN ('macro', 'market', 'technical')
);

DO $$
DECLARE
    constraint_name TEXT;
BEGIN
    FOR constraint_name IN
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_namespace nsp ON nsp.oid = rel.relnamespace
        WHERE nsp.nspname = current_schema()
          AND rel.relname = 'ai_category_insights'
          AND con.contype = 'u'
          AND pg_get_constraintdef(con.oid) = 'UNIQUE (user_id, category, date)'
    LOOP
        EXECUTE format('ALTER TABLE ai_category_insights DROP CONSTRAINT %I', constraint_name);
    END LOOP;
END $$;

DROP INDEX IF EXISTS uq_ai_category_insights_user_category_date;

DO $$
DECLARE
    index_row RECORD;
BEGIN
    FOR index_row IN
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = current_schema()
          AND tablename = 'ai_category_insights'
          AND indexdef ILIKE 'CREATE UNIQUE INDEX%'
          AND regexp_replace(indexdef, '\\s+', ' ', 'g') ~ '\\(user_id, category, date\\)$'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I', index_row.indexname);
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_category_insights_user_category_symbol_date
ON ai_category_insights(user_id, category, symbol, date);

CREATE INDEX IF NOT EXISTS idx_ai_category_insights_symbol_date
ON ai_category_insights(symbol, date DESC);
"""
