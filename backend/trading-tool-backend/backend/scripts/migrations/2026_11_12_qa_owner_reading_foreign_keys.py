"""Prevent late owner-scoped writes after temporary QA user cleanup.

Keep existing foreign-key delete actions. Add a NOT VALID cascading key only
where none exists, leaving historical orphan rows untouched while checking
new references. The temporary QA cleanup handles non-cascading child rows.
"""

SQL = """
DO $guard$
DECLARE
    table_name text;
    column_number smallint;
    existing_count integer;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'market_data_indicators', 'macro_data', 'technical_indicators',
        'market_indicator_rules', 'macro_indicator_rules',
        'technical_indicator_rules', 'system_logs'
    ] LOOP
        SELECT a.attnum INTO column_number
        FROM pg_attribute a
        WHERE a.attrelid = to_regclass('public.' || table_name)
          AND a.attname = 'user_id' AND a.atttypid = 'integer'::regtype
          AND NOT a.attisdropped;
        IF column_number IS NULL THEN
            RAISE EXCEPTION 'qa owner guard schema mismatch: %', table_name;
        END IF;

        SELECT count(*) INTO existing_count
        FROM pg_constraint c
        WHERE c.contype = 'f'
          AND c.conrelid = to_regclass('public.' || table_name)
          AND c.confrelid = 'users'::regclass
          AND c.conkey = ARRAY[column_number]::smallint[];
        -- Existing foreign keys, including SET NULL or RESTRICT, already
        -- reject late writes after owner deletion. Cleanup deletes this
        -- child's rows under a parent FOR UPDATE lock before deletion.
        IF existing_count = 0 THEN
            EXECUTE format(
                'ALTER TABLE public.%I ADD CONSTRAINT %I '
                || 'FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE NOT VALID',
                table_name, 'fk_' || table_name || '_user_qa_guard'
            );
        END IF;
    END LOOP;
END;
$guard$;
"""
