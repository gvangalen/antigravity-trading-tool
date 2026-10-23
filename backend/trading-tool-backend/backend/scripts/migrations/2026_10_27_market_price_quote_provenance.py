"""Persist the unit and provider of each market price snapshot.

Historic rows stay unknown: the current catalog quote must never be used to
reinterpret a price that was saved before its own quote was recorded.
"""

SQL = """
ALTER TABLE market_data
    ADD COLUMN IF NOT EXISTS quote_currency VARCHAR(8),
    ADD COLUMN IF NOT EXISTS price_provider VARCHAR(80);
"""
