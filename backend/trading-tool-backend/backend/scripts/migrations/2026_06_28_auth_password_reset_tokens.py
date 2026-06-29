"""Create password reset token storage for auth hardening."""

SQL = """
CREATE TABLE IF NOT EXISTS auth_password_reset_tokens (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    locale VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ,
    revoked_reason VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_auth_password_reset_tokens_user_id
ON auth_password_reset_tokens (user_id);

CREATE INDEX IF NOT EXISTS idx_auth_password_reset_tokens_expires_at
ON auth_password_reset_tokens (expires_at);
"""
