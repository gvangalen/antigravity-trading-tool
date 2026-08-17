"""Create FINN Core V2 policy, proposal, confirmation, and eligibility storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_policy_decisions (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    orchestrator_result_id TEXT NOT NULL REFERENCES finn_v2_orchestrator_results(id) ON DELETE CASCADE,
    snapshot_id TEXT NULL REFERENCES finn_v2_state_snapshots(id) ON DELETE SET NULL,
    validation_id TEXT NULL REFERENCES finn_v2_validation_results(id) ON DELETE SET NULL,
    policy_class TEXT NOT NULL,
    operation_type TEXT NULL,
    allowed BOOLEAN NOT NULL,
    proposal_allowed BOOLEAN NOT NULL,
    confirmation_required BOOLEAN NOT NULL,
    step_up_required BOOLEAN NOT NULL,
    execution_allowed BOOLEAN NOT NULL,
    shadow_safe BOOLEAN NOT NULL,
    evidence_set_hash TEXT NULL,
    decision_json JSONB NOT NULL,
    policy_version TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_finn_v2_policy_run_version UNIQUE (run_id, policy_version)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_policy_run_id ON finn_v2_policy_decisions (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_policy_user_id ON finn_v2_policy_decisions (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_policy_class ON finn_v2_policy_decisions (policy_class);
CREATE INDEX IF NOT EXISTS idx_finn_v2_policy_operation_type ON finn_v2_policy_decisions (operation_type);
CREATE INDEX IF NOT EXISTS idx_finn_v2_policy_created_at ON finn_v2_policy_decisions (created_at);

CREATE TABLE IF NOT EXISTS finn_v2_proposals (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    policy_decision_id TEXT NOT NULL REFERENCES finn_v2_policy_decisions(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    operation_type TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NULL,
    asset TEXT NULL,
    payload_json JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    requires_step_up_auth BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ux_finn_v2_proposal_user_idempotency UNIQUE (user_id, idempotency_key),
    CONSTRAINT ux_finn_v2_proposal_run_payload UNIQUE (run_id, payload_hash)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_proposals_run_id ON finn_v2_proposals (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_proposals_user_id ON finn_v2_proposals (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_proposals_status ON finn_v2_proposals (status);
CREATE INDEX IF NOT EXISTS idx_finn_v2_proposals_operation_type ON finn_v2_proposals (operation_type);
CREATE INDEX IF NOT EXISTS idx_finn_v2_proposals_created_at ON finn_v2_proposals (created_at);

CREATE TABLE IF NOT EXISTS finn_v2_confirmations (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES finn_v2_proposals(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    confirmed BOOLEAN NOT NULL,
    already_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ux_finn_v2_confirmations_proposal_user UNIQUE (proposal_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_confirmations_proposal_id ON finn_v2_confirmations (proposal_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_confirmations_user_id ON finn_v2_confirmations (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_confirmations_created_at ON finn_v2_confirmations (created_at);

CREATE TABLE IF NOT EXISTS finn_v2_eligibility_decisions (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES finn_v2_proposals(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    eligible BOOLEAN NOT NULL,
    policy_class TEXT NOT NULL,
    decision_json JSONB NOT NULL,
    eligibility_version TEXT NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_eligibility_run_id ON finn_v2_eligibility_decisions (run_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eligibility_user_id ON finn_v2_eligibility_decisions (user_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eligibility_proposal_id ON finn_v2_eligibility_decisions (proposal_id);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eligibility_policy_class ON finn_v2_eligibility_decisions (policy_class);
CREATE INDEX IF NOT EXISTS idx_finn_v2_eligibility_checked_at ON finn_v2_eligibility_decisions (checked_at);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_eligibility_decisions;
DROP TABLE IF EXISTS finn_v2_confirmations;
DROP TABLE IF EXISTS finn_v2_proposals;
DROP TABLE IF EXISTS finn_v2_policy_decisions;
"""
