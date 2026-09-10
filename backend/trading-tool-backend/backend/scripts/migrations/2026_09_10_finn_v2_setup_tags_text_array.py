"""Keep the FINN setup adapter and PostgreSQL schema on one tags contract."""

SQL = """
CREATE OR REPLACE FUNCTION finn_v2_jsonb_to_text_array(value JSONB)
RETURNS TEXT[]
LANGUAGE SQL
IMMUTABLE
AS $$
    SELECT COALESCE(array_agg(item), ARRAY[]::TEXT[])
    FROM jsonb_array_elements_text(COALESCE(value, '[]'::JSONB)) AS item
$$;

DO $$
DECLARE
    tags_type TEXT;
BEGIN
    SELECT data_type
      INTO tags_type
      FROM information_schema.columns
     WHERE table_schema = current_schema()
       AND table_name = 'setups'
       AND column_name = 'tags';

    IF tags_type = 'jsonb' THEN
        ALTER TABLE setups ALTER COLUMN tags DROP DEFAULT;
        ALTER TABLE setups
            ALTER COLUMN tags TYPE TEXT[]
            USING finn_v2_jsonb_to_text_array(tags);
    END IF;

    IF tags_type IS NOT NULL THEN
        ALTER TABLE setups
            ALTER COLUMN tags SET DEFAULT ARRAY[]::TEXT[];
    END IF;
END $$;

DROP FUNCTION IF EXISTS finn_v2_jsonb_to_text_array(JSONB);
"""
