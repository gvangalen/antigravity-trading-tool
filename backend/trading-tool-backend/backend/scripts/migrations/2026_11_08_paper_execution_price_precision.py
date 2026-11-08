"""Keep stored unit prices as precise as the dated Paper execution evidence."""

SQL = """
-- Existing two-decimal prices remain unchanged. New fills keep enough
-- precision to audit the same source-price and FX conversion in JSONB.
-- This migration is run on every deploy. Skip ALTER's heavy table lock once
-- a column already has the target type.
DO $$
BEGIN
    IF (SELECT format_type(atttypid, atttypmod)
        FROM pg_attribute
        WHERE attrelid = 'bot_orders'::regclass
          AND attname = 'executed_price_eur' AND NOT attisdropped)
       IS DISTINCT FROM 'numeric(30,10)' THEN
        ALTER TABLE bot_orders
            ALTER COLUMN executed_price_eur TYPE NUMERIC(30, 10);
    END IF;
    IF (SELECT format_type(atttypid, atttypmod)
        FROM pg_attribute
        WHERE attrelid = 'bot_ledger'::regclass
          AND attname = 'price_eur' AND NOT attisdropped)
       IS DISTINCT FROM 'numeric(30,10)' THEN
        ALTER TABLE bot_ledger
            ALTER COLUMN price_eur TYPE NUMERIC(30, 10);
    END IF;
END;
$$;
"""

# Narrowing these columns again would discard newly recorded fill precision.
ROLLBACK_SQL = ""
