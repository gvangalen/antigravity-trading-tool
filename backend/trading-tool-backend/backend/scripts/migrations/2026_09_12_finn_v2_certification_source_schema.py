"""Restore additive source-schema compatibility for active FINN V2 readers."""

SQL = """
ALTER TABLE daily_scores
    ADD COLUMN IF NOT EXISTS macro_interpretation TEXT,
    ADD COLUMN IF NOT EXISTS macro_top_contributors JSONB,
    ADD COLUMN IF NOT EXISTS technical_interpretation TEXT,
    ADD COLUMN IF NOT EXISTS technical_top_contributors JSONB,
    ADD COLUMN IF NOT EXISTS market_interpretation TEXT,
    ADD COLUMN IF NOT EXISTS market_top_contributors JSONB;

ALTER TABLE bot_portfolios
    ADD COLUMN IF NOT EXISTS cash_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS position_qty NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS invested_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS avg_entry NUMERIC,
    ADD COLUMN IF NOT EXISTS realized_pnl_eur NUMERIC NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

CREATE TABLE IF NOT EXISTS ai_reflections (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    indicator TEXT NOT NULL,
    raw_score NUMERIC,
    ai_score NUMERIC,
    compliance NUMERIC,
    comment TEXT,
    recommendation TEXT,
    date DATE NOT NULL DEFAULT CURRENT_DATE,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_ai_reflections_user_category_date
    ON ai_reflections (user_id, category, date, timestamp DESC);

CREATE TABLE IF NOT EXISTS daily_reports (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    report_date DATE NOT NULL DEFAULT CURRENT_DATE,
    status TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_daily_reports_user_date
    ON daily_reports (user_id, report_date DESC);
"""
