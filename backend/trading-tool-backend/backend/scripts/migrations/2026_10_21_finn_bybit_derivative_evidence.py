"""Private, owner-scoped Bybit derivative execution and order evidence.

All tables are read-side only. Spot fills remain in their existing table.
"""

SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_exchange_import_sources_owner_id
ON finn_exchange_import_sources(user_id, id);

CREATE TABLE IF NOT EXISTS finn_bybit_derivative_attempts (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    last_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error_code TEXT NULL
);

CREATE TABLE IF NOT EXISTS finn_bybit_derivative_cursors (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('linear','inverse')),
    cursor_json JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending','partial','ready','error')),
    coverage_start_at TIMESTAMPTZ NOT NULL,
    coverage_through_at TIMESTAMPTZ NULL,
    last_success_at TIMESTAMPTZ NULL,
    last_error_code TEXT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, source_id, category),
    FOREIGN KEY (user_id, source_id)
      REFERENCES finn_exchange_import_sources(user_id, id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS finn_bybit_derivative_orders (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('linear','inverse')),
    order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    position_idx INTEGER NOT NULL CHECK (position_idx IN (0,1,2)),
    side TEXT NOT NULL CHECK (side IN ('buy','sell')),
    reduce_only BOOLEAN NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, source_id, category, order_id),
    FOREIGN KEY (user_id, source_id, category)
      REFERENCES finn_bybit_derivative_cursors(user_id, source_id, category) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS finn_bybit_derivative_executions (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_id BIGINT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('linear','inverse')),
    exec_id TEXT NOT NULL,
    order_id TEXT NULL,
    symbol TEXT NOT NULL,
    base_currency TEXT NULL,
    quote_currency TEXT NULL,
    settle_currency TEXT NOT NULL,
    contract_size NUMERIC NULL,
    exec_type TEXT NOT NULL,
    side TEXT NULL CHECK (side IN ('buy','sell')),
    qty NUMERIC NULL CHECK (qty > 0),
    price NUMERIC NULL CHECK (price > 0),
    execution_value NUMERIC NULL CHECK (execution_value > 0),
    fee_amount NUMERIC NULL,
    fee_currency TEXT NULL,
    closed_size NUMERIC NULL CHECK (closed_size >= 0),
    seq BIGINT NULL,
    traded_at TIMESTAMPTZ NOT NULL,
    evidence_status TEXT NOT NULL CHECK
      (evidence_status IN ('trade_order_pending','trade_order_resolved','material_event_unmodeled')),
    position_idx INTEGER NULL CHECK (position_idx IN (0,1,2)),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    order_lookup_at TIMESTAMPTZ NULL,
    UNIQUE (user_id, source_id, category, exec_id),
    FOREIGN KEY (user_id, source_id, category)
      REFERENCES finn_bybit_derivative_cursors(user_id, source_id, category) ON DELETE CASCADE
);
ALTER TABLE finn_bybit_derivative_executions
  ADD COLUMN IF NOT EXISTS order_lookup_at TIMESTAMPTZ NULL;
CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_bybit_derivative_executions_owner_id
ON finn_bybit_derivative_executions(user_id, id);
CREATE INDEX IF NOT EXISTS ix_finn_bybit_derivative_exec_stream
ON finn_bybit_derivative_executions(user_id, source_id, category, symbol, position_idx, traded_at, id);
CREATE INDEX IF NOT EXISTS ix_finn_bybit_derivative_exec_order
ON finn_bybit_derivative_executions(user_id, source_id, category, order_id)
WHERE evidence_status='trade_order_pending';

ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS derivative_category TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS position_idx INTEGER NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS direction TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS settle_currency TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS native_pnl NUMERIC NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS native_pnl_status TEXT NULL;
ALTER TABLE finn_trade_reviews ADD COLUMN IF NOT EXISTS fee_legs_by_currency JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE finn_trade_reviews DROP CONSTRAINT IF EXISTS ck_finn_trade_reviews_origin;
ALTER TABLE finn_trade_reviews ADD CONSTRAINT ck_finn_trade_reviews_origin CHECK (
  (origin='bot_position' AND closure_basis='ledger_flat' AND bot_id IS NOT NULL
   AND opening_ledger_id IS NOT NULL AND closing_ledger_id IS NOT NULL
   AND entry_value_eur IS NOT NULL AND exit_value_eur IS NOT NULL
   AND entry_price_eur IS NOT NULL AND exit_price_eur IS NOT NULL
   AND pnl_eur_before_fees IS NOT NULL AND exchange_name IS NULL
   AND attested_at IS NULL AND derivative_category IS NULL)
  OR
  (origin='exchange_user_attested' AND closure_basis='user_confirmed'
   AND bot_id IS NULL AND opening_ledger_id IS NULL AND closing_ledger_id IS NULL
   AND execution_environment='live' AND exchange_name IN ('bitvavo','bybit')
   AND attested_at IS NOT NULL AND jsonb_array_length(attestation_source_ids) > 0
   AND derivative_category IS NULL
   AND ((pnl_status='before_fees_eur' AND entry_value_eur IS NOT NULL
         AND exit_value_eur IS NOT NULL AND entry_price_eur IS NOT NULL
         AND exit_price_eur IS NOT NULL AND pnl_eur_before_fees IS NOT NULL)
        OR (pnl_status='not_comparable' AND entry_value_eur IS NULL
            AND exit_value_eur IS NULL AND entry_price_eur IS NULL
            AND exit_price_eur IS NULL AND pnl_eur_before_fees IS NULL)))
  OR
  (origin='bybit_derivative_user_attested' AND closure_basis='user_confirmed'
   AND bot_id IS NULL AND opening_ledger_id IS NULL AND closing_ledger_id IS NULL
   AND execution_environment='live' AND exchange_name='bybit'
   AND attested_at IS NOT NULL AND jsonb_array_length(attestation_source_ids)=1
   AND derivative_category IN ('linear','inverse') AND position_idx IN (0,1,2)
   AND direction IN ('long','short') AND settle_currency IS NOT NULL
   AND pnl_status='not_comparable' AND native_pnl_status='unavailable'
   AND native_pnl IS NULL AND entry_value_eur IS NULL AND exit_value_eur IS NULL
   AND entry_price_eur IS NULL AND exit_price_eur IS NULL AND pnl_eur_before_fees IS NULL)
);

CREATE TABLE IF NOT EXISTS finn_bybit_derivative_review_attestations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    idempotency_key UUID NOT NULL,
    episode_digest TEXT NOT NULL,
    review_id BIGINT NOT NULL,
    source_id BIGINT NOT NULL,
    category TEXT NOT NULL CHECK (category IN ('linear','inverse')),
    symbol TEXT NOT NULL,
    position_idx INTEGER NOT NULL CHECK (position_idx IN (0,1,2)),
    closure_confirmed BOOLEAN NOT NULL CHECK (closure_confirmed),
    confirmation_version INTEGER NOT NULL DEFAULT 1,
    confirmation_method TEXT NOT NULL DEFAULT 'authenticated_api_attestation',
    confirmation_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id,idempotency_key),
    UNIQUE (user_id,review_id),
    UNIQUE (user_id,source_id,category,symbol,position_idx,episode_digest),
    FOREIGN KEY (user_id,source_id,category)
      REFERENCES finn_bybit_derivative_cursors(user_id,source_id,category) ON DELETE RESTRICT,
    FOREIGN KEY (user_id,review_id)
      REFERENCES finn_trade_reviews(user_id,id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS finn_bybit_derivative_review_allocations (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    execution_id BIGINT NOT NULL,
    review_id BIGINT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('open','close')),
    qty NUMERIC NOT NULL CHECK (qty>0),
    PRIMARY KEY (user_id,execution_id,review_id,role),
    FOREIGN KEY (user_id,execution_id)
      REFERENCES finn_bybit_derivative_executions(user_id,id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id,review_id)
      REFERENCES finn_trade_reviews(user_id,id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_finn_bybit_derivative_alloc_execution
ON finn_bybit_derivative_review_allocations(user_id,execution_id);
"""
