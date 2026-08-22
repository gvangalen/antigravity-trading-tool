"""Create the durable FINN V2 dispatch outbox used by visible and shadow runs."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_v2_run_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL UNIQUE REFERENCES finn_v2_runs(id) ON DELETE CASCADE,
    task_id TEXT NOT NULL UNIQUE,
    queue TEXT NOT NULL,
    routing_rule TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    owner TEXT NULL,
    claimed_at TIMESTAMPTZ NULL,
    lease_expires_at TIMESTAMPTZ NULL,
    next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_error_code TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    dispatched_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    CONSTRAINT ck_finn_v2_dispatch_status CHECK (status IN (
        'pending', 'dispatching', 'dispatched', 'claimed', 'running',
        'completed', 'retryable_failure', 'terminal_failure'
    )),
    CONSTRAINT ck_finn_v2_dispatch_attempt_count CHECK (attempt_count >= 0)
);
CREATE INDEX IF NOT EXISTS idx_finn_v2_dispatch_recovery
ON finn_v2_run_dispatches (status, next_attempt_at, lease_expires_at);
"""

ROLLBACK_SQL = """
DROP TABLE IF EXISTS finn_v2_run_dispatches;
"""
