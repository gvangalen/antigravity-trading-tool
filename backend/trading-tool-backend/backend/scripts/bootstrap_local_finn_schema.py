#!/usr/bin/env python3
"""Create the non-production baseline required by historical FINN migrations."""
from backend.infrastructure.database import Base, sync_engine
from backend.infrastructure import models  # noqa: F401 - register ORM metadata
from sqlalchemy import text


LEGACY_BASELINE = """
-- The score writer upserts one row per owner, asset and day. Older disposable
-- databases may have been created before DailyScore declared this key;
-- create_all cannot add it to an existing table.
CREATE UNIQUE INDEX IF NOT EXISTS daily_scores_user_symbol_report_date_unique
    ON daily_scores (user_id, symbol, report_date);
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
-- Custom strategy curves exist in the historical product database but are
-- absent from ORM create_all. FINN's Smart DCA confirmation needs the same
-- owner-scoped store in the disposable parity database.
CREATE TABLE IF NOT EXISTS indicator_curves (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    domain VARCHAR NOT NULL,
    indicator VARCHAR NOT NULL,
    curve JSONB NOT NULL,
    name VARCHAR NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    is_preset BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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
-- The paper decision tables are legacy product tables, not ORM models. A
-- disposable FINN stack needs them to execute a confirmed DCA strategy.
CREATE TABLE IF NOT EXISTS bot_decisions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    bot_id INTEGER NOT NULL REFERENCES bot_configs(id),
    strategy_id INTEGER REFERENCES strategies(id),
    setup_id INTEGER REFERENCES setups(id),
    symbol VARCHAR,
    decision_date DATE NOT NULL,
    decision_ts TIMESTAMP,
    action VARCHAR,
    confidence VARCHAR,
    amount_eur NUMERIC,
    scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status VARCHAR NOT NULL DEFAULT 'planned',
    executed_by VARCHAR,
    executed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, bot_id, decision_date)
);
CREATE TABLE IF NOT EXISTS bot_trade_plans (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    bot_id INTEGER NOT NULL REFERENCES bot_configs(id),
    decision_id INTEGER NOT NULL UNIQUE REFERENCES bot_decisions(id),
    symbol VARCHAR,
    side VARCHAR,
    entry_plan JSONB,
    stop_loss JSONB,
    targets JSONB,
    risk_json JSONB,
    status VARCHAR NOT NULL DEFAULT 'planned',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS bot_orders (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), decision_id INTEGER, status TEXT DEFAULT 'pending');
CREATE TABLE IF NOT EXISTS bot_executions (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), bot_order_id INTEGER REFERENCES bot_orders(id));
CREATE TABLE IF NOT EXISTS bot_ledger (id SERIAL PRIMARY KEY, user_id INTEGER REFERENCES users(id), order_id INTEGER REFERENCES bot_orders(id), entry_type TEXT);
CREATE TABLE IF NOT EXISTS bot_portfolios (id SERIAL PRIMARY KEY, bot_id INTEGER REFERENCES bot_configs(id), user_id INTEGER REFERENCES users(id), symbol TEXT);
CREATE TABLE IF NOT EXISTS global_market_insights (id SERIAL PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS regime_memory (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date DATE NOT NULL,
    regime_label VARCHAR,
    confidence NUMERIC,
    signals_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    narrative TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, date)
);

-- ``create_all`` deliberately never mutates legacy tables.  The safe FINN
-- adapters use the long-standing service schemas below, so a disposable local
-- runtime must receive the same additive baseline before action-matrix tests.
ALTER TABLE setups
    ADD COLUMN IF NOT EXISTS setup_type VARCHAR DEFAULT 'trade',
    ADD COLUMN IF NOT EXISTS dca_frequency VARCHAR,
    ADD COLUMN IF NOT EXISTS dca_day VARCHAR,
    ADD COLUMN IF NOT EXISTS dca_month_day INTEGER,
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

-- Match production's INTEGER column even when an older disposable parity
-- database was bootstrapped with VARCHAR. This catches asyncpg type errors
-- during local confirmation instead of after deployment.
ALTER TABLE setups
    ALTER COLUMN dca_month_day TYPE INTEGER
    USING NULLIF(dca_month_day::text, '')::integer;

ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS name VARCHAR,
    ADD COLUMN IF NOT EXISTS canonical_name VARCHAR,
    ADD COLUMN IF NOT EXISTS symbol VARCHAR,
    ADD COLUMN IF NOT EXISTS timeframe VARCHAR,
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

ALTER TABLE bot_orders
    ADD COLUMN IF NOT EXISTS bot_id INTEGER REFERENCES bot_configs(id),
    ADD COLUMN IF NOT EXISTS symbol VARCHAR,
    ADD COLUMN IF NOT EXISTS side VARCHAR,
    ADD COLUMN IF NOT EXISTS order_type VARCHAR,
    ADD COLUMN IF NOT EXISTS quote_amount_eur NUMERIC,
    ADD COLUMN IF NOT EXISTS estimated_price_eur NUMERIC,
    ADD COLUMN IF NOT EXISTS estimated_qty NUMERIC,
    ADD COLUMN IF NOT EXISTS executed_price_eur NUMERIC,
    ADD COLUMN IF NOT EXISTS executed_qty NUMERIC,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

ALTER TABLE bot_executions
    ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS filled_qty NUMERIC,
    ADD COLUMN IF NOT EXISTS avg_fill_price NUMERIC,
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;

-- The repository reads these columns even when a disposable fixture has not
-- executed a trade. ``create_all`` cannot expand the historical stub above.
ALTER TABLE bot_ledger
    ADD COLUMN IF NOT EXISTS bot_id INTEGER REFERENCES bot_configs(id),
    ADD COLUMN IF NOT EXISTS decision_id INTEGER REFERENCES bot_decisions(id),
    ADD COLUMN IF NOT EXISTS symbol VARCHAR,
    ADD COLUMN IF NOT EXISTS cash_delta_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS qty_delta NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS price_eur NUMERIC,
    ADD COLUMN IF NOT EXISTS note TEXT,
    ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

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
