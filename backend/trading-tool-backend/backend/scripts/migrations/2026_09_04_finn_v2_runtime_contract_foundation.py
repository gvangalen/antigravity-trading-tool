"""Persist one authoritative, revisioned FINN V2 runtime contract per run."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_runtime_contracts (
    contract_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES finn_v2_conversations(id) ON DELETE CASCADE,
    trace_id TEXT NOT NULL,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    contract_version TEXT NOT NULL,
    revision INTEGER NOT NULL DEFAULT 0 CHECK (revision >= 0),
    state_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    terminal_projection_json JSONB NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_finn_v2_runtime_contract_conversation ON finn_v2_runtime_contracts (conversation_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_runtime_contract_trace ON finn_v2_runtime_contracts (trace_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_runtime_contract_user ON finn_v2_runtime_contracts (user_id);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_runtime_contracts;
"""
