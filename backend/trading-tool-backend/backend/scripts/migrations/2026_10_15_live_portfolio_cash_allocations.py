"""Explicit, owner-scoped allocation of a shared Live broker's free EUR cash.

This is presentation attribution only. Order sizing and exchange balances do
not read this table. A bot limit is never copied into an allocation.
"""

SQL = """
CREATE TABLE IF NOT EXISTS live_portfolio_cash_allocations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id INTEGER NOT NULL REFERENCES bot_configs(id) ON DELETE CASCADE,
    exchange_name TEXT NOT NULL,
    amount_eur NUMERIC(20, 2) NOT NULL CHECK (amount_eur >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, bot_id)
);
CREATE INDEX IF NOT EXISTS idx_live_portfolio_cash_allocations_owner_exchange
    ON live_portfolio_cash_allocations(user_id, exchange_name);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS live_portfolio_cash_allocations;"
