"""Speed up latest-market-data reads used by dashboard and overview cards."""

SQL = """
CREATE INDEX IF NOT EXISTS idx_market_data_symbol_timestamp_desc
ON market_data (symbol, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_data_timestamp_desc
ON market_data (timestamp DESC);
"""
