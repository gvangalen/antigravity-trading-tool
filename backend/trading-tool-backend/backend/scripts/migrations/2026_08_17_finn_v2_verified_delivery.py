"""Create FINN Core V2 verifier and verified-response storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_verifier_results (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    draft_id TEXT NOT NULL,
    reasoning_result_id TEXT NULL REFERENCES finn_v2_reasoning_results(id) ON DELETE SET NULL,
    passed BOOLEAN NOT NULL,
    action TEXT NOT NULL,
    result_json JSONB NOT NULL,
    reason_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    deterministic_version TEXT NOT NULL,
    semantic_verifier_used BOOLEAN NOT NULL DEFAULT FALSE,
    semantic_model TEXT NULL,
    repair_attempt INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_finn_v2_verifier_action CHECK (action IN ('deliver', 'repair_once', 'downgrade_to_fact', 'downgrade_to_clarification', 'downgrade_to_unavailable', 'reject')),
    CONSTRAINT ck_finn_v2_verifier_repair CHECK (repair_attempt IN (0, 1))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_verifier_run_id ON finn_v2_verifier_results (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_verifier_user_id ON finn_v2_verifier_results (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_verifier_reasoning_id ON finn_v2_verifier_results (reasoning_result_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_verifier_created ON finn_v2_verifier_results (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS finn_v2_verified_responses (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    verifier_result_id TEXT NOT NULL REFERENCES finn_v2_verifier_results(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    verifier_status TEXT NOT NULL,
    response_json JSONB NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    response_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_finn_v2_verified_response UNIQUE (run_id, response_version),
    CONSTRAINT ck_finn_v2_verified_mode CHECK (mode IN ('FACT', 'EVALUATION', 'PROPOSAL', 'ACTION', 'CLARIFICATION', 'UNAVAILABLE')),
    CONSTRAINT ck_finn_v2_verified_status CHECK (verifier_status IN ('passed', 'repaired', 'downgraded'))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_verified_run_id ON finn_v2_verified_responses (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_verified_user_id ON finn_v2_verified_responses (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_verified_verifier_id ON finn_v2_verified_responses (verifier_result_id);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_verified_responses;
DROP TABLE IF EXISTS finn_v2_verifier_results;
"""
