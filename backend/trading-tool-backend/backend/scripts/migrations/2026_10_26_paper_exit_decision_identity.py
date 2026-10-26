"""Expand decision identity without removing the legacy daily uniqueness.

This first release is backward compatible with the previous bot writer. Paper
auto-exits remain disabled until a later, separately accepted cutover release.
"""

SQL = """
ALTER TABLE bot_decisions
    ADD COLUMN IF NOT EXISTS decision_kind TEXT NOT NULL DEFAULT 'assessment';
ALTER TABLE bot_decisions
    ADD COLUMN IF NOT EXISTS position_open_ledger_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='bot_decisions_kind_valid') THEN
        ALTER TABLE bot_decisions ADD CONSTRAINT bot_decisions_kind_valid
            CHECK (decision_kind IN ('assessment', 'paper_exit'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='bot_decisions_exit_position_required') THEN
        ALTER TABLE bot_decisions ADD CONSTRAINT bot_decisions_exit_position_required
            CHECK (decision_kind <> 'paper_exit' OR position_open_ledger_id IS NOT NULL);
    END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS bot_decisions_one_assessment_per_day
    ON bot_decisions (user_id, bot_id, decision_date)
    WHERE decision_kind = 'assessment';
CREATE UNIQUE INDEX IF NOT EXISTS bot_decisions_one_exit_per_position
    ON bot_decisions (user_id, bot_id, position_open_ledger_id)
    WHERE decision_kind = 'paper_exit';

"""
