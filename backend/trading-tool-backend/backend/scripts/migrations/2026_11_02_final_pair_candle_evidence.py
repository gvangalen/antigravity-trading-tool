"""Mark verified, completed direct-pair candles separately from quote snapshots.

Legacy rows remain unmarked. The exact-market history bootstrap refetches real
final candles and marks only those returned as final by the provider.
"""

SQL = """
ALTER TABLE market_data
    ADD COLUMN IF NOT EXISTS is_final_candle BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_market_data_final_pair_candles
    ON market_data (market_id, source_observed_at DESC)
    WHERE market_id IS NOT NULL AND is_final_candle = TRUE;
"""
