"""Allow explicitly user-attested exchange round trips in FINN's review table.

The bot ledger projector keeps its existing defaults. Exchange reviews reserve
exact imported fills in a separate owner-scoped table; no trading state changes.
"""

SQL = """
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT 'bot_position';
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS closure_basis TEXT NOT NULL DEFAULT 'ledger_flat';
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS base_currency TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS pnl_status TEXT NOT NULL DEFAULT 'before_fees_eur';
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS cash_legs_by_currency JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS exchange_name TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS attested_at TIMESTAMPTZ NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS attestation_source_ids JSONB NOT NULL DEFAULT '[]'::jsonb;
UPDATE finn_trade_reviews SET base_currency=symbol WHERE base_currency IS NULL AND origin='bot_position';
ALTER TABLE finn_trade_reviews ALTER COLUMN base_currency SET NOT NULL;

ALTER TABLE finn_trade_reviews ALTER COLUMN bot_id DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN opening_ledger_id DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN closing_ledger_id DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN entry_value_eur DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN exit_value_eur DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN entry_price_eur DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN exit_price_eur DROP NOT NULL;
ALTER TABLE finn_trade_reviews ALTER COLUMN pnl_eur_before_fees DROP NOT NULL;

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='ck_finn_trade_reviews_origin') THEN
    ALTER TABLE finn_trade_reviews ADD CONSTRAINT ck_finn_trade_reviews_origin CHECK (
      (origin='bot_position' AND closure_basis='ledger_flat' AND bot_id IS NOT NULL
       AND opening_ledger_id IS NOT NULL AND closing_ledger_id IS NOT NULL
       AND entry_value_eur IS NOT NULL AND exit_value_eur IS NOT NULL
       AND entry_price_eur IS NOT NULL AND exit_price_eur IS NOT NULL
       AND pnl_eur_before_fees IS NOT NULL AND exchange_name IS NULL
       AND attested_at IS NULL)
      OR
      (origin='exchange_user_attested' AND closure_basis='user_confirmed'
       AND bot_id IS NULL AND opening_ledger_id IS NULL AND closing_ledger_id IS NULL
       AND execution_environment='live' AND exchange_name IN ('bitvavo','bybit')
       AND attested_at IS NOT NULL AND jsonb_array_length(attestation_source_ids) > 0
       AND ((pnl_status='before_fees_eur' AND entry_value_eur IS NOT NULL
             AND exit_value_eur IS NOT NULL AND entry_price_eur IS NOT NULL
             AND exit_price_eur IS NOT NULL AND pnl_eur_before_fees IS NOT NULL)
            OR (pnl_status='not_comparable' AND entry_value_eur IS NULL
                AND exit_value_eur IS NULL AND entry_price_eur IS NULL
                AND exit_price_eur IS NULL AND pnl_eur_before_fees IS NULL)))
    );
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_trade_reviews_owner_id
ON finn_trade_reviews(user_id, id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_exchange_import_fills_owner_id
ON finn_exchange_import_fills(user_id, id);

CREATE TABLE IF NOT EXISTS finn_exchange_review_fill_reservations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exchange_fill_id BIGINT NOT NULL,
    review_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, exchange_fill_id),
    FOREIGN KEY (user_id, exchange_fill_id)
      REFERENCES finn_exchange_import_fills(user_id, id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, review_id)
      REFERENCES finn_trade_reviews(user_id, id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_finn_exchange_review_fill_reservations_review
ON finn_exchange_review_fill_reservations(user_id, review_id);

CREATE TABLE IF NOT EXISTS finn_exchange_review_attestations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idempotency_key UUID NOT NULL,
    request_digest TEXT NOT NULL,
    review_id BIGINT NOT NULL,
    same_account_confirmed BOOLEAN NOT NULL,
    closure_confirmed BOOLEAN NOT NULL CHECK (closure_confirmed),
    confirmation_version INTEGER NOT NULL CHECK (confirmation_version > 0),
    confirmation_method TEXT NOT NULL CHECK (confirmation_method='web_checkbox'),
    identity_basis TEXT NOT NULL CHECK (identity_basis IN
      ('single_credential_epoch','provider_uid','credential_epoch_user_confirmed')),
    closure_confirmation_text TEXT NOT NULL,
    same_account_confirmation_text TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, idempotency_key),
    UNIQUE (user_id, review_id),
    FOREIGN KEY (user_id, review_id)
      REFERENCES finn_trade_reviews(user_id, id) ON DELETE CASCADE
);
"""
