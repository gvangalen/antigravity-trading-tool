"""Create FINN Core V2 orchestrator result storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_orchestrator_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orchestrator_version TEXT NOT NULL,
    analysis_version TEXT NOT NULL,
    planning_version TEXT NOT NULL,
    interaction_mode TEXT NOT NULL,
    subject_scopes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    optional_domains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    tool_plan_json JSONB NOT NULL,
    snapshot_id TEXT NULL REFERENCES finn_v2_state_snapshots(id) ON DELETE SET NULL,
    validation_id TEXT NULL REFERENCES finn_v2_validation_results(id) ON DELETE SET NULL,
    outcome TEXT NOT NULL,
    selected_clarification_json JSONB NULL,
    unavailable_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    uncertainty_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_finn_v2_orchestrator_run_version UNIQUE (run_id, orchestrator_version),
    CONSTRAINT ck_finn_v2_orchestrator_mode CHECK (interaction_mode IN ('READ', 'EVALUATE', 'CREATE_PROPOSAL', 'ACTION_PROPOSAL', 'CLARIFICATION', 'CONFIRMATION', 'EXECUTION', 'UNAVAILABLE', 'CAPABILITY', 'FACT', 'EVALUATION', 'PROPOSAL', 'ACTION')),
    CONSTRAINT ck_finn_v2_orchestrator_outcome CHECK (outcome IN ('reasoning_ready', 'clarification_required', 'unavailable', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_orchestrator_run_id
ON finn_v2_orchestrator_results (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_orchestrator_user_id
ON finn_v2_orchestrator_results (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_orchestrator_interaction_mode
ON finn_v2_orchestrator_results (interaction_mode);

CREATE INDEX IF NOT EXISTS idx_finn_v2_orchestrator_outcome
ON finn_v2_orchestrator_results (outcome);

CREATE INDEX IF NOT EXISTS idx_finn_v2_orchestrator_user_created
ON finn_v2_orchestrator_results (user_id, created_at DESC);
"""


ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_orchestrator_results;
"""
