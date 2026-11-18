"""Allow a dayless benchmark trigger through the legacy setup schedule check.

Production has an older ``dca_logic_check`` that requires a weekday for every
weekly DCA. Keep its exact predicate for calendar and legacy rows, adding only
the new benchmark-triggered exception. The marker makes the expansion safe to
replay and also forbids calendar fields on future benchmark-triggered rows.
"""

SQL = """
DO $$
DECLARE
    previous_rule text;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'setups'::regclass
          AND conname = 'setups_smart_dca_schedule_valid'
    ) THEN
        SELECT pg_get_expr(conbin, conrelid)
          INTO previous_rule
          FROM pg_constraint
         WHERE conrelid = 'setups'::regclass
           AND conname = 'dca_logic_check'
           AND contype = 'c';

        IF previous_rule IS NOT NULL THEN
            ALTER TABLE setups DROP CONSTRAINT dca_logic_check;
            EXECUTE format(
                'ALTER TABLE setups ADD CONSTRAINT dca_logic_check '
                || 'CHECK ((%s) OR (setup_type = ''dca'' '
                || 'AND dca_trigger_mode = ''benchmark'' '
                || 'AND dca_frequency IN (''daily'', ''weekly'', ''monthly'') '
                || 'AND dca_day IS NULL AND dca_month_day IS NULL)) NOT VALID',
                previous_rule
            );
        END IF;

        ALTER TABLE setups ADD CONSTRAINT setups_smart_dca_schedule_valid
            CHECK (
                dca_trigger_mode <> 'benchmark'
                OR (COALESCE(setup_type = 'dca', FALSE)
                    AND COALESCE(dca_frequency IN ('daily', 'weekly', 'monthly'), FALSE)
                    AND dca_day IS NULL AND dca_month_day IS NULL)
            ) NOT VALID;
    END IF;
END $$;
"""
