"""Owner-wide Paper reserve and independent, explicitly confirmed Paper trades.

Existing bot cash remains in its bot ledger. The reserve starts at zero and
receives cash only through an explicit transfer; deployment never mints funds.
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
DROP TABLE IF EXISTS paper_reserve_transfers;
DROP TABLE IF EXISTS paper_reserve_accounts;
"""
