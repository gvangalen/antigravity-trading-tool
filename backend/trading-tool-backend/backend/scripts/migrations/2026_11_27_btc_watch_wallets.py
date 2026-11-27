"""Owner-scoped, read-only Bitcoin account balances from an external indexer."""

SQL = """
CREATE TABLE IF NOT EXISTS btc_watch_wallets (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label VARCHAR(80) NOT NULL,
    xpub_encrypted TEXT NOT NULL,
    xpub_fingerprint CHAR(64) NOT NULL,
    script_type VARCHAR(24) NOT NULL CHECK (script_type IN
        ('legacy', 'nested_segwit', 'native_segwit', 'taproot')),
    confirmed_sats BIGINT,
    unconfirmed_sats BIGINT,
    sync_status VARCHAR(24) NOT NULL DEFAULT 'pending' CHECK (sync_status IN
        ('pending', 'available', 'unavailable')),
    provider VARCHAR(40),
    fetched_at TIMESTAMPTZ,
    last_attempt_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, xpub_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_btc_watch_wallets_owner
    ON btc_watch_wallets (user_id, id);
CREATE INDEX IF NOT EXISTS idx_btc_watch_wallets_due
    ON btc_watch_wallets (last_attempt_at NULLS FIRST, id);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS btc_watch_wallets;"
