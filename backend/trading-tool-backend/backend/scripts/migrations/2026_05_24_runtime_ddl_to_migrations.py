"""Move startup schema hotfixes into an explicit idempotent migration.

This migration contains the DDL that used to run from ``backend/main.py`` on
every application startup. Run it before deploying backend code with read-only
startup behavior.
"""

SQL = """
ALTER TABLE global_market_insights
ADD COLUMN IF NOT EXISTS avg_score numeric(5,2);

CREATE TABLE IF NOT EXISTS conversation_state (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
    current_flow VARCHAR,
    asset VARCHAR,
    slots JSONB DEFAULT '{}'::jsonb,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE ai_category_insights
ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS trace_id VARCHAR;

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS completion_status VARCHAR DEFAULT 'success';

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS parser_recovery_triggered BOOLEAN DEFAULT false;

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS confidence_score NUMERIC(5, 2);

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS safety_guardrail_triggered BOOLEAN DEFAULT false;

ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS symbol VARCHAR DEFAULT 'BTC';

CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_user_id ON ai_usage_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_trace_id ON ai_usage_logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_timestamp ON ai_usage_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_ai_usage_logs_completion_status ON ai_usage_logs(completion_status);

CREATE TABLE IF NOT EXISTS chat_sessions (
    id VARCHAR PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
    role VARCHAR NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    intent VARCHAR,
    actions JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id ON chat_sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_updated_at ON chat_sessions(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages(session_id);

CREATE TABLE IF NOT EXISTS ai_pending_actions (
    id VARCHAR PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    trace_id VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_ai_pending_actions_user_id ON ai_pending_actions(user_id);

CREATE TABLE IF NOT EXISTS ai_intelligence_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    type VARCHAR NOT NULL,
    symbol VARCHAR,
    title VARCHAR NOT NULL,
    description TEXT NOT NULL,
    severity VARCHAR NOT NULL DEFAULT 'info',
    payload JSONB DEFAULT '{}'::jsonb,
    status VARCHAR NOT NULL DEFAULT 'active',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_intelligence_events_user_id ON ai_intelligence_events(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_intelligence_events_status ON ai_intelligence_events(status);

ALTER TABLE bot_configs
ADD COLUMN IF NOT EXISTS symbol VARCHAR;

ALTER TABLE bot_configs
DROP CONSTRAINT IF EXISTS bot_configs_cadence_check;

ALTER TABLE bot_configs
ADD CONSTRAINT bot_configs_cadence_check
CHECK (cadence IN ('hourly', 'daily', 'weekly', 'monthly', 'custom'));

ALTER TABLE bot_orders
ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_orders_user_idempotency_key
ON bot_orders (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;
"""
