"""Store one owner-scoped reflection for each completed Amsterdam calendar week."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_weekly_trade_reflections (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    week_end DATE NOT NULL,
    summary JSONB NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, week_start),
    CHECK (week_end = week_start + 7)
);
CREATE INDEX IF NOT EXISTS ix_finn_weekly_trade_reflections_owner_recent
ON finn_weekly_trade_reflections(user_id, week_start DESC);
"""
