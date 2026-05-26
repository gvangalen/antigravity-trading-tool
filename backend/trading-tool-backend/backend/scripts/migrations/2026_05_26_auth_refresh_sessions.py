"""Add refresh-session storage for token rotation and revocation."""

SQL = """
CREATE TABLE IF NOT EXISTS auth_refresh_sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    jti VARCHAR NOT NULL UNIQUE,
    token_hash VARCHAR NOT NULL UNIQUE,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP,
    rotated_at TIMESTAMP,
    revoked_at TIMESTAMP,
    revoked_reason VARCHAR,
    replaced_by_jti VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_sessions_user_id
ON auth_refresh_sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_sessions_expires_at
ON auth_refresh_sessions(expires_at);

CREATE INDEX IF NOT EXISTS idx_auth_refresh_sessions_revoked_at
ON auth_refresh_sessions(revoked_at);
"""
