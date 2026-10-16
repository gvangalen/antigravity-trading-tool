"""Stage normalized Bitvavo account movements without altering trading state."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_exchange_import_movements (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL REFERENCES finn_exchange_import_sources(id) ON DELETE CASCADE,
    provider_transaction_id TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    sent_currency TEXT NULL,
    sent_amount NUMERIC NULL CHECK (sent_amount > 0),
    received_currency TEXT NULL,
    received_amount NUMERIC NULL CHECK (received_amount > 0),
    fee_currency TEXT NULL,
    fee_amount NUMERIC NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    evidence_status TEXT NOT NULL CHECK (evidence_status IN ('complete', 'unsupported')),
    unsupported_reason TEXT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, source_id, provider_transaction_id),
    CHECK ((sent_currency IS NULL) = (sent_amount IS NULL)),
    CHECK ((received_currency IS NULL) = (received_amount IS NULL)),
    CHECK ((fee_currency IS NULL) = (fee_amount IS NULL)),
    CHECK ((evidence_status = 'complete' AND unsupported_reason IS NULL) OR
           (evidence_status = 'unsupported' AND unsupported_reason IS NOT NULL)),
    CHECK (evidence_status = 'unsupported' OR
           sent_currency IS NOT NULL OR received_currency IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS ix_finn_exchange_movements_owner_source_time
ON finn_exchange_import_movements(user_id, source_id, occurred_at, id);
"""
