"""Owner-scoped FINN coach updates, separate from legacy intelligence cards."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_coach_feed_items (
    id UUID PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_id TEXT,
    symbol TEXT,
    priority SMALLINT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK (status IN ('unread', 'read', 'handled', 'archived', 'resolved')),
    fingerprint TEXT NOT NULL,
    evidence JSONB NOT NULL,
    source_observed_at TIMESTAMPTZ,
    copy_json JSONB NOT NULL,
    copy_source TEXT NOT NULL DEFAULT 'fact_fallback',
    copy_attempts SMALLINT NOT NULL DEFAULT 0,
    copy_last_attempt_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE finn_coach_feed_items
    DROP CONSTRAINT IF EXISTS finn_coach_feed_items_user_id_event_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_finn_coach_feed_current_event
    ON finn_coach_feed_items(user_id, event_key)
    WHERE status IN ('unread', 'read');
CREATE INDEX IF NOT EXISTS idx_finn_coach_feed_event_history
    ON finn_coach_feed_items(user_id, event_key, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_finn_coach_feed_owner_status
    ON finn_coach_feed_items(user_id, status, updated_at DESC);
CREATE TABLE IF NOT EXISTS finn_coach_feed_runtime (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    initial_decision_id BIGINT NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO finn_coach_feed_runtime (singleton, initial_decision_id)
SELECT TRUE, COALESCE(MAX(id), 0) FROM bot_decisions
ON CONFLICT (singleton) DO NOTHING;
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS finn_coach_feed_runtime; DROP TABLE IF EXISTS finn_coach_feed_items;"
