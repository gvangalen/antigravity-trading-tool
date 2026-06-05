"""Scope bot portfolio state by symbol instead of bot_id alone.

This keeps portfolio state from collapsing when a bot changes symbol or when
older single-asset assumptions leak into newer multi-asset paths.
"""

SQL = """
UPDATE bot_portfolios bp
SET symbol = COALESCE(
    NULLIF(UPPER(bp.symbol), ''),
    NULLIF(UPPER(bc.symbol), ''),
    NULLIF(UPPER(st.symbol), ''),
    'BTC'
)
FROM bot_configs bc
LEFT JOIN strategies s ON s.id = bc.strategy_id
LEFT JOIN setups st ON st.id = s.setup_id
WHERE bc.id = bp.bot_id
  AND bc.user_id = bp.user_id
  AND (bp.symbol IS NULL OR BTRIM(bp.symbol) = '');

DO $$
DECLARE
    index_name text;
BEGIN
    ALTER TABLE bot_portfolios
    DROP CONSTRAINT IF EXISTS bot_portfolios_bot_id_key;

    FOR index_name IN
        SELECT indexname
        FROM pg_indexes
        WHERE schemaname = 'public'
          AND tablename = 'bot_portfolios'
          AND indexdef ILIKE 'CREATE UNIQUE INDEX%ON %.bot_portfolios% (bot_id)%'
    LOOP
        EXECUTE format('DROP INDEX IF EXISTS %I', index_name);
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_portfolios_bot_symbol
ON bot_portfolios (bot_id, symbol);
"""
