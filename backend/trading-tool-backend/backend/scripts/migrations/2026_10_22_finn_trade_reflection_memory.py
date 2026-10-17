"""Preserve trade dialogue provenance and explicit user-confirmed lessons."""

SQL = """
ALTER TABLE finn_trade_reviews
  ADD COLUMN IF NOT EXISTS plan_provenance JSONB NULL;
ALTER TABLE finn_trade_review_messages
  ADD COLUMN IF NOT EXISTS input_revision BIGINT NULL;
ALTER TABLE finn_trade_review_messages
  ADD COLUMN IF NOT EXISTS evidence_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Legacy messages have no provable evidence revision. Keep NULL as unknown.
CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_trade_review_messages_owner_review_id
ON finn_trade_review_messages(user_id,review_id,id);

CREATE TABLE IF NOT EXISTS finn_trade_review_lessons (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    review_id BIGINT NOT NULL,
    lesson_text TEXT NOT NULL CHECK (char_length(lesson_text) <= 500),
    status TEXT NOT NULL CHECK (status IN ('active','withdrawn')),
    confirmed_at TIMESTAMPTZ NULL,
    evidence_revision BIGINT NOT NULL,
    source_message_id BIGINT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id,review_id),
    FOREIGN KEY (user_id,review_id)
      REFERENCES finn_trade_reviews(user_id,id) ON DELETE CASCADE,
    FOREIGN KEY (user_id,review_id,source_message_id)
      REFERENCES finn_trade_review_messages(user_id,review_id,id) ON DELETE RESTRICT,
    CHECK ((status='active' AND confirmed_at IS NOT NULL AND char_length(trim(lesson_text)) BETWEEN 10 AND 500)
        OR (status='withdrawn' AND confirmed_at IS NULL))
);
CREATE INDEX IF NOT EXISTS ix_finn_trade_review_lessons_owner_active
ON finn_trade_review_lessons(user_id,confirmed_at DESC,review_id DESC)
WHERE status='active';
"""
