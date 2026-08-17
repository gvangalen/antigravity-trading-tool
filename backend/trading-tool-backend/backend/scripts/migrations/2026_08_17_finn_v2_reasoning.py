"""Create FINN Core V2 reasoning result storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_reasoning_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orchestrator_result_id TEXT NOT NULL REFERENCES finn_v2_orchestrator_results(id) ON DELETE CASCADE,
    policy_decision_id TEXT NOT NULL REFERENCES finn_v2_policy_decisions(id) ON DELETE CASCADE,
    snapshot_id TEXT NOT NULL REFERENCES finn_v2_state_snapshots(id) ON DELETE CASCADE,
    validation_id TEXT NOT NULL REFERENCES finn_v2_validation_results(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    context_version TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    reasoning_version TEXT NOT NULL,
    model TEXT NULL,
    result_json JSONB NULL,
    error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    input_tokens INTEGER NULL,
    output_tokens INTEGER NULL,
    reasoning_tokens INTEGER NULL,
    latency_ms INTEGER NULL,
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    CONSTRAINT ux_finn_v2_reasoning_dedupe UNIQUE (run_id, context_version, evidence_set_hash, prompt_version, model),
    CONSTRAINT ck_finn_v2_reasoning_status CHECK (status IN ('pending', 'generating', 'ready', 'unavailable', 'failed')),
    CONSTRAINT ck_finn_v2_reasoning_mode CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE')),
    CONSTRAINT ck_finn_v2_reasoning_retry CHECK (retry_count IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_run_id ON finn_v2_reasoning_results (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_user_id ON finn_v2_reasoning_results (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_status ON finn_v2_reasoning_results (status);
CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_mode ON finn_v2_reasoning_results (mode);
CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_input_hash ON finn_v2_reasoning_results (input_hash);
CREATE INDEX IF NOT EXISTS idx_finn_v2_reasoning_user_created ON finn_v2_reasoning_results (user_id, created_at DESC);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_reasoning_results;
"""
