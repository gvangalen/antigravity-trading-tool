"""Start a forward-only, owner-scoped FINN position-review record.

The watermark and baseline are captured together. Existing open positions are
quarantined until flat; old paper/live orders cannot be classified reliably.
Run this migration before deploying the review API.
"""

SQL = """
LOCK TABLE bot_ledger, bot_portfolios, bot_orders IN SHARE ROW EXCLUSIVE MODE;
CREATE TABLE IF NOT EXISTS finn_trade_review_cutover (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    ledger_high_watermark BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS finn_trade_review_baselines (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    position_qty NUMERIC NOT NULL,
    PRIMARY KEY (user_id, bot_id, symbol)
);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM finn_trade_review_cutover WHERE singleton=TRUE) THEN
    INSERT INTO finn_trade_review_cutover (singleton, ledger_high_watermark)
    SELECT TRUE, COALESCE(MAX(id), 0) FROM bot_ledger;
    INSERT INTO finn_trade_review_baselines (user_id, bot_id, symbol, position_qty)
    SELECT user_id, bot_id, symbol, COALESCE(position_qty, 0)
    FROM bot_portfolios;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS finn_trade_order_context (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    order_id BIGINT NOT NULL,
    decision_id BIGINT NULL,
    plan_snapshot JSONB NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, order_id)
);

CREATE OR REPLACE FUNCTION finn_capture_order_plan() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO finn_trade_order_context (user_id, order_id, decision_id, plan_snapshot)
  SELECT NEW.user_id, NEW.id, NEW.decision_id,
    CASE WHEN p.decision_id IS NULL THEN NULL ELSE jsonb_build_object(
      'entry_plan', p.entry_plan, 'stop_loss', p.stop_loss,
      'targets', p.targets, 'risk', p.risk_json
    ) END
  FROM (SELECT 1) seed
  LEFT JOIN bot_trade_plans p ON p.decision_id = NEW.decision_id
    AND p.user_id = NEW.user_id;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_finn_capture_order_plan ON bot_orders;
CREATE TRIGGER trg_finn_capture_order_plan
AFTER INSERT ON bot_orders FOR EACH ROW EXECUTE FUNCTION finn_capture_order_plan();

CREATE TABLE IF NOT EXISTS finn_trade_reviews (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    execution_environment TEXT NOT NULL CHECK (execution_environment IN ('paper', 'live')),
    execution_sources JSONB NOT NULL DEFAULT '[]'::jsonb,
    opening_ledger_id BIGINT NOT NULL,
    closing_ledger_id BIGINT NOT NULL,
    entry_at TIMESTAMPTZ NOT NULL,
    exit_at TIMESTAMPTZ NOT NULL,
    entry_qty NUMERIC NOT NULL,
    entry_value_eur NUMERIC NOT NULL,
    exit_value_eur NUMERIC NOT NULL,
    entry_price_eur NUMERIC NOT NULL,
    exit_price_eur NUMERIC NOT NULL,
    pnl_eur_before_fees NUMERIC NOT NULL,
    plan_snapshot JSONB NULL,
    fills JSONB NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, opening_ledger_id),
    UNIQUE (user_id, closing_ledger_id)
);
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS execution_sources JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE INDEX IF NOT EXISTS ix_finn_trade_reviews_user_exit
ON finn_trade_reviews (user_id, exit_at DESC, id DESC);

CREATE TABLE IF NOT EXISTS finn_trade_review_dirty_users (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    generation BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE OR REPLACE FUNCTION finn_mark_trade_review_dirty() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.entry_type = 'execute' THEN
    INSERT INTO finn_trade_review_dirty_users (user_id, generation)
    VALUES (NEW.user_id, 1)
    ON CONFLICT (user_id) DO UPDATE SET
      generation = finn_trade_review_dirty_users.generation + 1,
      updated_at = NOW();
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_finn_trade_review_dirty ON bot_ledger;
CREATE TRIGGER trg_finn_trade_review_dirty
AFTER INSERT ON bot_ledger FOR EACH ROW EXECUTE FUNCTION finn_mark_trade_review_dirty();

CREATE OR REPLACE FUNCTION finn_mark_trade_review_order_dirty() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status OR
     OLD.execution_environment IS DISTINCT FROM NEW.execution_environment THEN
    INSERT INTO finn_trade_review_dirty_users (user_id, generation)
    VALUES (NEW.user_id, 1)
    ON CONFLICT (user_id) DO UPDATE SET
      generation = finn_trade_review_dirty_users.generation + 1,
      updated_at = NOW();
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_finn_trade_review_order_dirty ON bot_orders;
CREATE TRIGGER trg_finn_trade_review_order_dirty
AFTER UPDATE OF status, execution_environment ON bot_orders
FOR EACH ROW EXECUTE FUNCTION finn_mark_trade_review_order_dirty();

CREATE OR REPLACE FUNCTION finn_mark_trade_review_decision_dirty() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.executed_by IS DISTINCT FROM NEW.executed_by THEN
    INSERT INTO finn_trade_review_dirty_users (user_id, generation)
    VALUES (NEW.user_id, 1)
    ON CONFLICT (user_id) DO UPDATE SET
      generation = finn_trade_review_dirty_users.generation + 1,
      updated_at = NOW();
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_finn_trade_review_decision_dirty ON bot_decisions;
CREATE TRIGGER trg_finn_trade_review_decision_dirty
AFTER UPDATE OF executed_by ON bot_decisions
FOR EACH ROW EXECUTE FUNCTION finn_mark_trade_review_decision_dirty();

CREATE TABLE IF NOT EXISTS finn_trade_review_screenshots (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    review_id BIGINT NOT NULL REFERENCES finn_trade_reviews(id) ON DELETE CASCADE,
    png_bytes BYTEA NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, review_id)
);

ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_json JSONB NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS input_revision BIGINT NOT NULL DEFAULT 0;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_model TEXT NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_reason TEXT NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS analysis_updated_at TIMESTAMPTZ NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS candles_json JSONB NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS candles_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS candles_reason TEXT NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS candles_updated_at TIMESTAMPTZ NULL;
ALTER TABLE finn_trade_reviews
ADD COLUMN IF NOT EXISTS candles_attempts INTEGER NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS ix_finn_trade_reviews_analysis_queue
ON finn_trade_reviews (analysis_status, exit_at, id);
CREATE INDEX IF NOT EXISTS ix_finn_trade_reviews_user_analysis_updated
ON finn_trade_reviews (user_id, analysis_updated_at);

CREATE TABLE IF NOT EXISTS finn_trade_review_messages (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    review_id BIGINT NOT NULL REFERENCES finn_trade_reviews(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'finn')),
    content TEXT NOT NULL,
    evidence_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    model TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_finn_trade_review_messages_owner
ON finn_trade_review_messages (user_id, review_id, id);

CREATE TABLE IF NOT EXISTS finn_trade_ai_call_attempts (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    review_id BIGINT NOT NULL REFERENCES finn_trade_reviews(id) ON DELETE CASCADE,
    purpose TEXT NOT NULL CHECK (purpose IN ('analysis', 'question')),
    input_revision BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_finn_trade_ai_call_attempts_user_time
ON finn_trade_ai_call_attempts (user_id, created_at DESC);
"""
