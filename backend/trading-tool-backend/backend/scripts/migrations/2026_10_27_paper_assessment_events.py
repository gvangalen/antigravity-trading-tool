"""Persist the outcome of a manual Paper reassessment separately from orders."""

SQL = """
CREATE TABLE IF NOT EXISTS bot_paper_assessments (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    bot_id BIGINT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decision_date DATE NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN (
        'not_due', 'already_executed', 'no_new_decision',
        'decision_created', 'paper_order_filled', 'execution_failed'
    )),
    trace_id TEXT,
    CONSTRAINT bot_paper_assessments_bot_fk
        FOREIGN KEY (bot_id) REFERENCES bot_configs(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_bot_paper_assessments_owner_latest
    ON bot_paper_assessments (user_id, bot_id, checked_at DESC, id DESC);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS bot_paper_assessments;"
