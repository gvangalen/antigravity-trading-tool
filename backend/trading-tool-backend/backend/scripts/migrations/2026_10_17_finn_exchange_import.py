"""Private read-only exchange fill staging and bounded import cursors.

This migration deliberately has no trigger on bot orders, portfolios or the
ledger. Provider executions remain a separate evidence stream.
"""

SQL = """
CREATE TABLE IF NOT EXISTS finn_exchange_import_sources (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange_name TEXT NOT NULL CHECK (exchange_name IN ('bitvavo','bybit')),
    identity_kind TEXT NOT NULL CHECK (identity_kind IN ('provider_uid','credential_epoch')),
    identity_hash TEXT NOT NULL,
    credential_fingerprint TEXT NOT NULL,
    cursor_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending'
      CHECK (status IN ('pending','partial','ready','error','identity_unverified')),
    coverage_start_at TIMESTAMPTZ NULL,
    coverage_through_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_error_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, exchange_name, identity_hash)
);
CREATE INDEX IF NOT EXISTS ix_finn_exchange_sources_owner
ON finn_exchange_import_sources(user_id, exchange_name, updated_at DESC);

CREATE TABLE IF NOT EXISTS finn_exchange_import_attempts (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange_name TEXT NOT NULL CHECK (exchange_name IN ('bitvavo','bybit')),
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error_code TEXT NULL,
    PRIMARY KEY (user_id, exchange_name)
);

CREATE TABLE IF NOT EXISTS finn_exchange_import_fills (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES finn_exchange_import_sources(id) ON DELETE CASCADE,
    exchange_trade_id TEXT NOT NULL,
    exchange_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    base_currency TEXT NOT NULL,
    quote_currency TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    qty NUMERIC NOT NULL CHECK (qty > 0),
    price_quote NUMERIC NOT NULL CHECK (price_quote > 0),
    cost_quote NUMERIC NOT NULL CHECK (cost_quote > 0),
    fee_amount NUMERIC NULL,
    fee_currency TEXT NULL,
    traded_at TIMESTAMPTZ NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, source_id, symbol, exchange_trade_id)
);
CREATE INDEX IF NOT EXISTS ix_finn_exchange_fills_owner_source_time
ON finn_exchange_import_fills(user_id, source_id, traded_at, id);
CREATE INDEX IF NOT EXISTS ix_finn_exchange_fills_owner_order
ON finn_exchange_import_fills(user_id, source_id, exchange_order_id);
"""
