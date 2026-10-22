"""Owner-scoped, idempotent Paper cash reallocations between bots."""

SQL = """
CREATE TABLE IF NOT EXISTS paper_cash_transfers (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    source_bot_id BIGINT NOT NULL,
    target_bot_id BIGINT NOT NULL,
    amount_eur NUMERIC(18, 2) NOT NULL CHECK (amount_eur > 0),
    idempotency_key VARCHAR(128) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT paper_cash_transfer_distinct_bots CHECK (source_bot_id <> target_bot_id),
    CONSTRAINT paper_cash_transfer_user_key UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_paper_cash_transfers_user_created
    ON paper_cash_transfers (user_id, created_at DESC);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS paper_cash_transfers;"
