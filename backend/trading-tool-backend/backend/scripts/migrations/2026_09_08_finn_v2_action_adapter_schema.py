"""Align legacy action tables with the existing FINN V2 adapter services.

The adapters have always delegated to SetupService, StrategyService and
BotService.  Older installations can retain minimal historical tables because
``CREATE TABLE IF NOT EXISTS`` does not add later columns.  This idempotent
migration makes that drift explicit instead of masking it in a test runner.
"""

SQL = """
CREATE TABLE IF NOT EXISTS active_strategy_snapshot (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    setup_id INTEGER NOT NULL REFERENCES setups(id) ON DELETE CASCADE,
    strategy_id INTEGER NOT NULL REFERENCES strategies(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL DEFAULT CURRENT_DATE,
    entry NUMERIC,
    targets TEXT,
    stop_loss NUMERIC,
    confidence_score NUMERIC,
    adjustment_reason TEXT,
    market_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    changes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, setup_id, snapshot_date)
);

ALTER TABLE setups
    ADD COLUMN IF NOT EXISTS setup_type VARCHAR DEFAULT 'trade',
    ADD COLUMN IF NOT EXISTS dca_frequency VARCHAR,
    ADD COLUMN IF NOT EXISTS dca_day VARCHAR,
    ADD COLUMN IF NOT EXISTS dca_month_day VARCHAR,
    ADD COLUMN IF NOT EXISTS account_type VARCHAR,
    ADD COLUMN IF NOT EXISTS min_investment NUMERIC,
    ADD COLUMN IF NOT EXISTS trend VARCHAR,
    ADD COLUMN IF NOT EXISTS score_logic VARCHAR,
    ADD COLUMN IF NOT EXISTS favorite BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS action VARCHAR,
    ADD COLUMN IF NOT EXISTS category VARCHAR,
    ADD COLUMN IF NOT EXISTS min_macro_score NUMERIC,
    ADD COLUMN IF NOT EXISTS max_macro_score NUMERIC,
    ADD COLUMN IF NOT EXISTS min_technical_score NUMERIC,
    ADD COLUMN IF NOT EXISTS max_technical_score NUMERIC,
    ADD COLUMN IF NOT EXISTS min_market_score NUMERIC,
    ADD COLUMN IF NOT EXISTS max_market_score NUMERIC,
    ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS last_validated TIMESTAMP;

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS name VARCHAR,
    ADD COLUMN IF NOT EXISTS setup_type VARCHAR,
    ADD COLUMN IF NOT EXISTS execution_mode VARCHAR,
    ADD COLUMN IF NOT EXISTS base_amount NUMERIC,
    ADD COLUMN IF NOT EXISTS decision_curve JSONB,
    ADD COLUMN IF NOT EXISTS decision_curve_id INTEGER,
    ADD COLUMN IF NOT EXISTS entry NUMERIC,
    ADD COLUMN IF NOT EXISTS targets TEXT[],
    ADD COLUMN IF NOT EXISTS stop_loss NUMERIC,
    ADD COLUMN IF NOT EXISTS explanation TEXT,
    ADD COLUMN IF NOT EXISTS risk_profile VARCHAR,
    ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE bot_configs
    ADD COLUMN IF NOT EXISTS name VARCHAR,
    ADD COLUMN IF NOT EXISTS mode VARCHAR DEFAULT 'manual',
    ADD COLUMN IF NOT EXISTS is_live BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS risk_profile VARCHAR DEFAULT 'balanced',
    ADD COLUMN IF NOT EXISTS budget_total_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS budget_daily_limit_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS budget_min_order_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS budget_max_order_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_asset_exposure_pct NUMERIC NOT NULL DEFAULT 100,
    ADD COLUMN IF NOT EXISTS base_currency VARCHAR DEFAULT 'EUR',
    ADD COLUMN IF NOT EXISTS last_run TIMESTAMP,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE daily_setup_scores
    ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_best BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS explanation TEXT,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
"""
