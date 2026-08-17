"""Create FINN Core V2 evidence, state snapshot, and validation storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_evidence_artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tool_call_id BIGINT NOT NULL REFERENCES finn_v2_tool_calls(id) ON DELETE CASCADE,
    tool_name TEXT NOT NULL,
    entity_type TEXT NULL,
    entity_id TEXT NULL,
    asset TEXT NULL,
    source TEXT NOT NULL,
    resolution_source TEXT NOT NULL,
    user_scoped BOOLEAN NOT NULL DEFAULT TRUE,
    source_as_of TIMESTAMPTZ NULL,
    freshness TEXT NOT NULL,
    availability TEXT NOT NULL,
    schema_name TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    payload_json JSONB NULL,
    error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    redacted_at TIMESTAMPTZ NULL,
    CONSTRAINT ux_finn_v2_evidence_tool_call UNIQUE (tool_call_id),
    CONSTRAINT ck_finn_v2_evidence_freshness CHECK (freshness IN ('fresh', 'stale', 'unknown', 'not_applicable')),
    CONSTRAINT ck_finn_v2_evidence_availability CHECK (availability IN ('available', 'stale', 'ambiguous', 'unavailable', 'not_collected'))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_run_id
ON finn_v2_evidence_artifacts (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_user_id
ON finn_v2_evidence_artifacts (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_tool_call_id
ON finn_v2_evidence_artifacts (tool_call_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_content_hash
ON finn_v2_evidence_artifacts (content_hash);

CREATE TABLE IF NOT EXISTS finn_v2_state_snapshots (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    assembly_version TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    snapshot_json JSONB NULL,
    assembled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    redacted_at TIMESTAMPTZ NULL,
    CONSTRAINT ux_finn_v2_state_run_revision UNIQUE (run_id, revision),
    CONSTRAINT ux_finn_v2_state_run_hash UNIQUE (run_id, evidence_set_hash)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_state_run_id
ON finn_v2_state_snapshots (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_state_user_id
ON finn_v2_state_snapshots (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_state_evidence_hash
ON finn_v2_state_snapshots (evidence_set_hash);

CREATE TABLE IF NOT EXISTS finn_v2_validation_results (
    id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL REFERENCES finn_v2_state_snapshots(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    schema_version TEXT NOT NULL,
    validator_version TEXT NOT NULL,
    evidence_set_hash TEXT NOT NULL,
    integrity_status TEXT NOT NULL,
    result_json JSONB NULL,
    validated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    redacted_at TIMESTAMPTZ NULL,
    CONSTRAINT ux_finn_v2_validation_snapshot_version UNIQUE (snapshot_id, validator_version),
    CONSTRAINT ck_finn_v2_validation_integrity CHECK (integrity_status IN ('valid', 'degraded', 'invalid'))
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_validation_snapshot_id
ON finn_v2_validation_results (snapshot_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_validation_run_id
ON finn_v2_validation_results (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_validation_user_id
ON finn_v2_validation_results (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_validation_integrity_status
ON finn_v2_validation_results (integrity_status);
"""


ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_validation_results;
DROP TABLE IF EXISTS finn_v2_state_snapshots;
DROP TABLE IF EXISTS finn_v2_evidence_artifacts;
"""
