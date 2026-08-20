"""Create isolated FINN Core V2 foundation storage.

Hot rollback is handled by FINN_V2_* feature flags. This file also exposes
ROLLBACK_SQL for controlled schema rollback outside the live request path.
"""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_conversations (
    id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_run_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_conversations_user_id
ON finn_v2_conversations (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_conversations_user_updated
ON finn_v2_conversations (user_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS finn_v2_runs (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES finn_v2_conversations(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    request_id TEXT NOT NULL,
    trace_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    transport TEXT NOT NULL CHECK (transport IN ('chat', 'stream')),
    visibility TEXT NOT NULL CHECK (visibility IN ('shadow', 'visible')),
    feature_mode TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('created', 'collecting', 'planned', 'blocked', 'completed', 'failed', 'canceled')),
    interaction_mode TEXT NULL CHECK (interaction_mode IS NULL OR interaction_mode IN ('READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'CAPABILITY', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION')),
    message TEXT NOT NULL,
    workspace_hints_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    client_context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    policy_json JSONB NULL,
    response_json JSONB NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,
    retryable BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    canceled_at TIMESTAMPTZ NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_finn_v2_runs_user_idempotency_key
ON finn_v2_runs (user_id, idempotency_key);

CREATE INDEX IF NOT EXISTS idx_finn_v2_runs_user_created
ON finn_v2_runs (user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finn_v2_runs_conversation_created
ON finn_v2_runs (conversation_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finn_v2_runs_trace_id
ON finn_v2_runs (trace_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_runs_status
ON finn_v2_runs (status);

CREATE TABLE IF NOT EXISTS finn_v2_run_traces (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    event_order INTEGER NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_finn_v2_run_traces_run_order UNIQUE (run_id, event_order)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_run_traces_run_id
ON finn_v2_run_traces (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_run_traces_user_id
ON finn_v2_run_traces (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_run_traces_trace_id
ON finn_v2_run_traces (trace_id);
"""


ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_run_traces;
DROP TABLE IF EXISTS finn_v2_runs;
DROP TABLE IF EXISTS finn_v2_conversations;
"""
