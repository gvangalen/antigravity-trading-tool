"""Expand FINN Core V2 run statuses for durable lifecycle ownership across Blocks 1-8."""

SQL = """
ALTER TABLE finn_v2_runs
    DROP CONSTRAINT IF EXISTS finn_v2_runs_status_check,
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_status,
    ADD CONSTRAINT ck_finn_v2_runs_status
    CHECK (
        status IN (
            'created',
            'queued',
            'collecting',
            'planned',
            'reasoning',
            'verifying',
            'clarification_required',
            'unavailable',
            'downgraded',
            'rejected',
            'blocked',
            'completed',
            'failed',
            'canceled'
        )
    );
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_runs
    DROP CONSTRAINT IF EXISTS ck_finn_v2_runs_status,
    ADD CONSTRAINT ck_finn_v2_runs_status
    CHECK (status IN ('created', 'collecting', 'planned', 'blocked', 'completed', 'failed', 'canceled'));
"""
