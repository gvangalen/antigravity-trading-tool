"""Persist consecutive Live broker valuation failures for feed deduplication."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_live_balance_observations (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    first_unavailable_at TIMESTAMPTZ,
    last_available_at TIMESTAMPTZ,
    last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS finn_live_balance_observations;"
