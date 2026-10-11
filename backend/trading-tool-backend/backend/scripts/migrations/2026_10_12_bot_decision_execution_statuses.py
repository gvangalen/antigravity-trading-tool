"""Align persisted bot-decision states with the atomic Paper/Live executor."""

SQL = """
ALTER TABLE bot_decisions
    DROP CONSTRAINT IF EXISTS bot_decisions_status_check;

ALTER TABLE bot_decisions
    ADD CONSTRAINT bot_decisions_status_check
    CHECK (status IN (
        'planned', 'ready', 'approved', 'executing', 'executed',
        'failed_execution', 'skipped', 'failed'
    )) NOT VALID;

ALTER TABLE bot_decisions
    VALIDATE CONSTRAINT bot_decisions_status_check;
"""
