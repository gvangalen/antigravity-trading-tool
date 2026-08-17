"""Create FINN Core V2 tool-call registry storage."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_tool_calls (
    id BIGSERIAL PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    trace_id TEXT NULL,
    tool_name TEXT NOT NULL,
    status TEXT NOT NULL,
    selector_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    success BOOLEAN NULL,
    resolution_source TEXT NULL,
    freshness_status TEXT NULL,
    result_summary_json JSONB NULL,
    error_codes_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ NULL,
    duration_ms INTEGER NULL,
    redacted_at TIMESTAMPTZ NULL,
    CONSTRAINT ck_finn_v2_tool_calls_status CHECK (status IN ('requested', 'executing', 'completed', 'failed')),
    CONSTRAINT ck_finn_v2_tool_calls_freshness CHECK (freshness_status IS NULL OR freshness_status IN ('fresh', 'stale', 'unknown', 'not_applicable')),
    CONSTRAINT ck_finn_v2_tool_calls_duration CHECK (duration_ms IS NULL OR duration_ms >= 0)
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_run_id
ON finn_v2_tool_calls (run_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_user_id
ON finn_v2_tool_calls (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_trace_id
ON finn_v2_tool_calls (trace_id);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_tool_name
ON finn_v2_tool_calls (tool_name);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_status
ON finn_v2_tool_calls (status);

CREATE INDEX IF NOT EXISTS idx_finn_v2_tool_calls_user_started
ON finn_v2_tool_calls (user_id, started_at DESC);
"""


ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_tool_calls;
"""
