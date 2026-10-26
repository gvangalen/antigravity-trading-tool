"""Keep a daily assessment and a Paper position exit as separate decisions.

Existing decisions remain assessments. An exit is unique for the opening
position ledger entry, including when the entry and exit happen on one day.
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

DO $$
DECLARE old_constraint RECORD;
BEGIN
    FOR old_constraint IN
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        WHERE t.relname = 'bot_decisions'
          AND c.contype = 'u'
          AND pg_get_constraintdef(c.oid) = 'UNIQUE (user_id, bot_id, decision_date)'
    LOOP
        EXECUTE format('ALTER TABLE bot_decisions DROP CONSTRAINT %I', old_constraint.conname);
    END LOOP;
END $$;

DO $$
DECLARE old_index RECORD;
BEGIN
    FOR old_index IN
        SELECT n.nspname, i.relname
        FROM pg_index x
        JOIN pg_class i ON i.oid=x.indexrelid
        JOIN pg_namespace n ON n.oid=i.relnamespace
        WHERE x.indrelid='bot_decisions'::regclass
          AND x.indisunique AND x.indpred IS NULL
          AND pg_get_indexdef(i.oid) LIKE '%(user_id, bot_id, decision_date)%'
          AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid=i.oid)
    LOOP
        EXECUTE format('DROP INDEX %I.%I', old_index.nspname, old_index.relname);
    END LOOP;
END $$;

"""
