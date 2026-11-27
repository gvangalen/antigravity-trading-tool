"""Owner-wide Paper reserve and independent, explicitly confirmed Paper trades.

Existing bot cash remains in its bot ledger. The reserve starts at zero and
receives cash only through an explicit transfer or owner-authorized virtual
Paper-budget adjustment; deployment never mints funds.
"""

SQL = """
CREATE TABLE IF NOT EXISTS paper_reserve_accounts (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    cash_eur NUMERIC(20, 2) NOT NULL DEFAULT 0 CHECK (cash_eur >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS paper_reserve_transfers (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id BIGINT NOT NULL REFERENCES bot_configs(id),
    direction TEXT NOT NULL CHECK (direction IN ('bot_to_reserve', 'reserve_to_bot')),
    amount_eur NUMERIC(20, 2) NOT NULL CHECK (amount_eur > 0),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_paper_reserve_transfers_owner_time
    ON paper_reserve_transfers (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_reserve_funding (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    direction TEXT NOT NULL CHECK (direction IN ('add', 'remove')),
    amount_eur NUMERIC(20, 2) NOT NULL CHECK (amount_eur > 0),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_paper_reserve_funding_owner_time
    ON paper_reserve_funding (user_id, created_at DESC);

-- Verified Paper value may consist solely of the owner's free reserve or a
-- discretionary position. Zero bots is valid, including after full withdrawal.
DO $$
DECLARE current_definition TEXT;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO current_definition
    FROM pg_constraint
    WHERE conrelid='portfolio_value_snapshots_v2'::regclass
      AND conname='portfolio_value_snapshots_v2_covered_bot_count_check';
    IF current_definition IS NULL OR
       current_definition LIKE '%covered_bot_count > 0%' THEN
        IF current_definition IS NOT NULL THEN
            ALTER TABLE portfolio_value_snapshots_v2
                DROP CONSTRAINT portfolio_value_snapshots_v2_covered_bot_count_check;
        END IF;
        ALTER TABLE portfolio_value_snapshots_v2
            ADD CONSTRAINT portfolio_value_snapshots_v2_covered_bot_count_check
            CHECK (covered_bot_count >= 0) NOT VALID;
        ALTER TABLE portfolio_value_snapshots_v2
            VALIDATE CONSTRAINT portfolio_value_snapshots_v2_covered_bot_count_check;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS paper_discretionary_orders (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    market_id BIGINT NOT NULL REFERENCES trading_markets(id),
    asset_symbol VARCHAR(20) NOT NULL,
    quote_currency VARCHAR(12) NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    notional_quote NUMERIC(20, 8) NOT NULL CHECK (notional_quote > 0),
    gross_eur NUMERIC(20, 2) NOT NULL CHECK (gross_eur > 0),
    fee_eur NUMERIC(20, 2) NOT NULL CHECK (fee_eur >= 0),
    quantity NUMERIC(28, 12) NOT NULL CHECK (quantity > 0),
    price_quote NUMERIC(28, 12) NOT NULL CHECK (price_quote > 0),
    price_eur NUMERIC(28, 12) NOT NULL CHECK (price_eur > 0),
    price_observed_at TIMESTAMPTZ NOT NULL,
    fx_observed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'filled' CHECK (status = 'filled'),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_paper_discretionary_orders_owner_time
    ON paper_discretionary_orders (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS paper_discretionary_positions (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    market_id BIGINT NOT NULL REFERENCES trading_markets(id),
    asset_symbol VARCHAR(20) NOT NULL,
    quote_currency VARCHAR(12) NOT NULL,
    quantity NUMERIC(28, 12) NOT NULL CHECK (quantity >= 0),
    invested_eur NUMERIC(20, 2) NOT NULL CHECK (invested_eur >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, market_id)
);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS paper_discretionary_positions;
DROP TABLE IF EXISTS paper_discretionary_orders;
DROP TABLE IF EXISTS paper_reserve_funding;
DROP TABLE IF EXISTS paper_reserve_transfers;
DROP TABLE IF EXISTS paper_reserve_accounts;
-- Keep the relaxed snapshot constraint: zero-bot history may already exist.
"""
