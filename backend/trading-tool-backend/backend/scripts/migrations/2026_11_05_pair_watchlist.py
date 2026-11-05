"""Allow independent watchlist rows for verified trading pairs."""

SQL = """
ALTER TABLE watchlists ADD COLUMN IF NOT EXISTS market_id BIGINT REFERENCES trading_markets(id);
ALTER TABLE watchlists DROP CONSTRAINT IF EXISTS ux_watchlists_user_symbol;
CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlists_user_market
    ON watchlists (user_id, market_id) WHERE market_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_watchlists_user_legacy_symbol
    ON watchlists (user_id, symbol) WHERE market_id IS NULL;
CREATE INDEX IF NOT EXISTS ix_watchlists_market_id ON watchlists (market_id);
"""
