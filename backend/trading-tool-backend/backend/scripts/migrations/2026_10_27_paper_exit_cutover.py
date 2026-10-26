"""Replace the legacy date-wide decision arbiter after old writers stop.

The Stage 1 assessment and per-position exit indexes must exist first. The
old unique key would reject an assessment and an exit on the same day.
"""

SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname=current_schema()
          AND tablename='bot_decisions'
          AND indexname='bot_decisions_one_assessment_per_day'
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_indexes WHERE schemaname=current_schema()
          AND tablename='bot_decisions'
          AND indexname='bot_decisions_one_exit_per_position'
    ) THEN
        RAISE EXCEPTION 'paper_exit_expand_required';
    END IF;
END $$;

DO $$
DECLARE old_constraint RECORD;
BEGIN
    FOR old_constraint IN
        SELECT c.conname
        FROM pg_constraint c
        WHERE c.conrelid='bot_decisions'::regclass
          AND c.contype='u'
          AND pg_get_constraintdef(c.oid)='UNIQUE (user_id, bot_id, decision_date)'
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
