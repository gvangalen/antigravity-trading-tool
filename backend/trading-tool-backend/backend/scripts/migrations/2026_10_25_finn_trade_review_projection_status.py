"""Persist per-user projection diagnostics for read-only review listing."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_trade_review_projection_status (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    legacy_or_ambiguous INTEGER NOT NULL DEFAULT 0,
    inconsistent INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""
