"""Create FINN Core V2 eval, cutover, and execution storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_eval_runs (
    id TEXT PRIMARY KEY,
    dataset_path TEXT NOT NULL,
    model_mode TEXT NOT NULL,
    total_cases INTEGER NOT NULL,
    passed_cases INTEGER NOT NULL,
    failed_cases INTEGER NOT NULL,
    result_json JSONB NOT NULL,
    blocking_gate_results_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    aggregate_scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    failure_case_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    real_model_validation_blocked BOOLEAN NOT NULL DEFAULT FALSE,
    blocker_code TEXT NULL,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost NUMERIC NOT NULL DEFAULT 0,
    latency_p50_ms NUMERIC NOT NULL DEFAULT 0,
    latency_p95_ms NUMERIC NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL
);

CREATE TABLE IF NOT EXISTS finn_v2_eval_case_results (
    id TEXT PRIMARY KEY,
    eval_run_id TEXT NOT NULL REFERENCES finn_v2_eval_runs(id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    category TEXT NOT NULL,
    fixture_user TEXT NOT NULL,
    passed BOOLEAN NOT NULL,
    blocking_passed BOOLEAN NOT NULL,
    expected_mode TEXT NOT NULL,
    actual_mode TEXT NULL,
    expected_outcome TEXT NOT NULL,
    actual_outcome TEXT NULL,
    dimension_scores_json JSONB NOT NULL,
    blocking_gate_results_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    latency_ms INTEGER NULL,
    model TEXT NULL,
    input_tokens INTEGER NULL,
    output_tokens INTEGER NULL,
    reasoning_tokens INTEGER NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_eval_case_run_id ON finn_v2_eval_case_results (eval_run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eval_case_case_id ON finn_v2_eval_case_results (case_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eval_case_category ON finn_v2_eval_case_results (category);

CREATE TABLE IF NOT EXISTS finn_v2_shadow_comparisons (
    id TEXT PRIMARY KEY,
    run_id TEXT NULL,
    user_id INTEGER NULL REFERENCES users(id) ON DELETE CASCADE,
    surface TEXT NOT NULL,
    outcome TEXT NOT NULL,
    result_json JSONB NOT NULL,
    reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_shadow_run_id ON finn_v2_shadow_comparisons (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_shadow_user_id ON finn_v2_shadow_comparisons (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_shadow_outcome ON finn_v2_shadow_comparisons (outcome);

CREATE TABLE IF NOT EXISTS finn_v2_release_gate_results (
    id TEXT PRIMARY KEY,
    eval_run_id TEXT NULL REFERENCES finn_v2_eval_runs(id) ON DELETE SET NULL,
    passed BOOLEAN NOT NULL,
    result_json JSONB NOT NULL,
    reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_release_gate_eval_run_id ON finn_v2_release_gate_results (eval_run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_release_gate_passed ON finn_v2_release_gate_results (passed);

CREATE TABLE IF NOT EXISTS finn_v2_executions (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES finn_v2_proposals(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    operation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    precondition_hash TEXT NOT NULL,
    postcondition_hash TEXT NULL,
    result_json JSONB NULL,
    error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    CONSTRAINT ux_finn_v2_execution_user_idempotency UNIQUE (user_id, idempotency_key),
    CONSTRAINT ux_finn_v2_execution_proposal UNIQUE (proposal_id)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_executions_run_id ON finn_v2_executions (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_executions_user_id ON finn_v2_executions (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_executions_status ON finn_v2_executions (status);
CREATE INDEX IF NOT EXISTS idx_finn_v2_executions_operation_type ON finn_v2_executions (operation_type);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_executions;
DROP TABLE IF EXISTS finn_v2_release_gate_results;
DROP TABLE IF EXISTS finn_v2_shadow_comparisons;
DROP TABLE IF EXISTS finn_v2_eval_case_results;
DROP TABLE IF EXISTS finn_v2_eval_runs;
"""
