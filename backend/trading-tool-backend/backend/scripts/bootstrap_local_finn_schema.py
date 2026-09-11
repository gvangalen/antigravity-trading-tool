#!/usr/bin/env python3
"""Create the non-production baseline required by historical FINN migrations."""
from backend.infrastructure.database import Base, sync_engine
from backend.infrastructure import models  # noqa: F401 - register ORM metadata
from sqlalchemy import text


LEGACY_BASELINE = """
ALTER TABLE user_indicator_configs
    ALTER COLUMN config_json TYPE JSONB USING config_json::text::jsonb,
    ALTER COLUMN config_json SET DEFAULT '{}'::jsonb,
    ALTER COLUMN config_json SET NOT NULL,
    ALTER COLUMN provenance TYPE TEXT,
    ALTER COLUMN provenance SET DEFAULT 'product_api',
    ALTER COLUMN provenance SET NOT NULL,
    ALTER COLUMN source_record_id TYPE BIGINT,
    ALTER COLUMN updated_at TYPE TIMESTAMP,
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP,
    ALTER COLUMN updated_at SET NOT NULL;
-- ``create_all`` reflects the current ORM's String fields as VARCHAR. The
-- canonical runtime-contract migration intentionally uses TEXT identifiers,
-- and its CREATE TABLE IF NOT EXISTS cannot correct a table that bootstrap
-- already created. Keep disposable local databases structurally equivalent
-- to the production migration result before replaying the remaining scripts.
ALTER TABLE finn_v2_runtime_contracts
    ALTER COLUMN contract_id TYPE TEXT,
    ALTER COLUMN run_id TYPE TEXT,
    ALTER COLUMN conversation_id TYPE TEXT,
    ALTER COLUMN trace_id TYPE TEXT,
    ALTER COLUMN contract_version TYPE TEXT;
ALTER TABLE finn_v2_evidence_artifacts
    ALTER COLUMN information_scope TYPE TEXT,
    ALTER COLUMN operation_id TYPE TEXT,
    ALTER COLUMN operation_contract_version TYPE TEXT;
ALTER TABLE finn_v2_tool_calls
    ALTER COLUMN operation_id TYPE TEXT,
    ALTER COLUMN operation_contract_version TYPE TEXT;
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = 'finn_v2_runtime_contracts'::regclass
          AND contype = 'u'
          AND conkey = ARRAY[
              (SELECT attnum FROM pg_attribute
               WHERE attrelid = 'finn_v2_runtime_contracts'::regclass AND attname = 'run_id')
          ]
    ) THEN
        ALTER TABLE finn_v2_runtime_contracts
            ADD CONSTRAINT finn_v2_runtime_contracts_run_id_key UNIQUE (run_id);
    END IF;
END $$;
-- ``create_all`` never alters an older local table. Keep the local baseline
-- compatible with the current asset catalog ORM before replaying migrations.
ALTER TABLE asset_catalog
    ADD COLUMN IF NOT EXISTS content_hash VARCHAR,
    ADD COLUMN IF NOT EXISTS payload_json JSONB,
    ADD COLUMN IF NOT EXISTS error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb;
CREATE TABLE IF NOT EXISTS strategies (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), setup_id INTEGER REFERENCES setups(id));
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
CREATE TABLE IF NOT EXISTS bot_configs (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), strategy_id INTEGER REFERENCES strategies(id), cadence TEXT DEFAULT 'daily', symbol TEXT);
CREATE TABLE IF NOT EXISTS bot_orders (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), decision_id INTEGER, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS bot_executions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), bot_order_id INTEGER REFERENCES bot_orders(id));
CREATE TABLE IF NOT EXISTS bot_ledger (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), order_id INTEGER REFERENCES bot_orders(id), entry_type TEXT);
CREATE TABLE IF NOT EXISTS bot_portfolios (id SERIAL PRIMARY KEY, bot_id INTEGER REFERENCES bot_configs(id), user_id INTEGER REFERENCES users(id), symbol TEXT);
CREATE TABLE IF NOT EXISTS global_market_insights (id SERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);

-- ``create_all`` deliberately never mutates legacy tables.  The safe FINN
-- adapters use the long-standing service schemas below, so a disposable local
-- runtime must receive the same additive baseline before action-matrix tests.
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

ALTER TABLE user_indicator_configs
    ALTER COLUMN updated_at SET DEFAULT CURRENT_TIMESTAMP;
"""


def main() -> None:
    Base.metadata.create_all(bind=sync_engine)
    with sync_engine.begin() as connection:
        connection.execute(text(LEGACY_BASELINE))


if __name__ == "__main__":
    main()
