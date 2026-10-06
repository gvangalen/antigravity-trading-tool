"""Keep the exact indicator calculation behind every stored category score."""

SQL = """
ALTER TABLE daily_scores
    ADD COLUMN IF NOT EXISTS calculated_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS indicator_evidence JSONB NULL;
CREATE INDEX IF NOT EXISTS idx_macro_data_score_v2
    ON macro_data (user_id, LOWER(name), source_observed_at DESC, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_market_data_history_v2
    ON market_data (symbol, source_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_market_indicator_score_v2
    ON market_data_indicators (user_id, symbol, name, source_observed_at DESC);
CREATE INDEX IF NOT EXISTS idx_technical_indicator_score_v2
    ON technical_indicators (user_id, symbol, indicator, source_observed_at DESC);
"""

ROLLBACK_SQL = """
DROP INDEX IF EXISTS idx_technical_indicator_score_v2;
DROP INDEX IF EXISTS idx_market_indicator_score_v2;
DROP INDEX IF EXISTS idx_market_data_history_v2;
DROP INDEX IF EXISTS idx_macro_data_score_v2;
ALTER TABLE daily_scores
    DROP COLUMN IF EXISTS indicator_evidence,
    DROP COLUMN IF EXISTS calculated_at;
"""
