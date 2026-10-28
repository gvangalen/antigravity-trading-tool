"""Add explicit market identity without assigning a pair to legacy evidence.

Existing base-symbol prices, scores, levels and bot positions cannot be
reinterpreted as EUR or USDT. Their market_id intentionally remains NULL.
The pair-aware writer cutover will replace base-only uniqueness separately.
"""

SQL = """
CREATE TABLE IF NOT EXISTS trading_markets (
    id BIGSERIAL PRIMARY KEY,
    asset_symbol VARCHAR NOT NULL REFERENCES asset_catalog(symbol),
    quote_currency VARCHAR(12) NOT NULL,
    venue VARCHAR(80) NOT NULL,
    provider VARCHAR(80) NOT NULL,
    provider_symbol VARCHAR(80) NOT NULL,
    tradingview_symbol VARCHAR(120) NOT NULL,
    source_verified_at TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (venue, provider_symbol),
    UNIQUE (asset_symbol, quote_currency, venue),
    CHECK (asset_symbol = UPPER(asset_symbol)),
    CHECK (quote_currency = UPPER(quote_currency)),
    CHECK (provider_symbol = UPPER(provider_symbol)),
    CHECK (venue = UPPER(venue))
);

-- A local bootstrap can create this table from an older ORM definition before
-- this migration runs. CREATE TABLE IF NOT EXISTS does not add its UNIQUE
-- clauses to that pre-existing table; preserve the ON CONFLICT arbiter.
CREATE UNIQUE INDEX IF NOT EXISTS ux_trading_markets_asset_quote_venue
    ON trading_markets (asset_symbol, quote_currency, venue);
CREATE UNIQUE INDEX IF NOT EXISTS ux_trading_markets_venue_provider_symbol
    ON trading_markets (venue, provider_symbol);
ALTER TABLE trading_markets ALTER COLUMN is_active SET DEFAULT TRUE;
ALTER TABLE trading_markets ALTER COLUMN created_at SET DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE setups ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE strategies ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE bot_configs ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE bot_decisions ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE bot_orders ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE bot_ledger ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE market_data ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE market_data_indicators ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE technical_indicators ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE user_indicator_configs ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE daily_scores ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);

CREATE INDEX IF NOT EXISTS idx_trading_markets_asset_quote
    ON trading_markets (asset_symbol, quote_currency, venue) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_market_data_market_observed
    ON market_data (market_id, source_observed_at DESC) WHERE market_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_daily_scores_market_date
    ON daily_scores (user_id, market_id, report_date DESC) WHERE market_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_user_indicator_configs_market
    ON user_indicator_configs (user_id, market_id, category, enabled)
    WHERE market_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_scores_legacy_market_scope
    ON daily_scores (user_id, symbol, report_date) WHERE market_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_daily_scores_exact_market_scope
    ON daily_scores (user_id, market_id, report_date) WHERE market_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_indicator_configs_legacy_market_scope
    ON user_indicator_configs (user_id, symbol, category, indicator)
    WHERE symbol IS NOT NULL AND market_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_indicator_configs_exact_market_scope
    ON user_indicator_configs (user_id, market_id, category, indicator)
    WHERE market_id IS NOT NULL;
"""
