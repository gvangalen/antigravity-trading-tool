"""Create mobile push token storage for native Expo notifications."""

SQL = """
CREATE TABLE IF NOT EXISTS mobile_push_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    push_token VARCHAR NOT NULL UNIQUE,
    device_name VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_mobile_push_tokens_user_id
ON mobile_push_tokens (user_id);

CREATE INDEX IF NOT EXISTS idx_mobile_push_tokens_created_at
ON mobile_push_tokens (created_at DESC);
"""
