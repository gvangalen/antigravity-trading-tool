"""Make user_indicator_configs the only runtime source for user indicator choices."""

SQL = r"""
ALTER TABLE user_indicator_configs
    ADD COLUMN IF NOT EXISTS config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS provenance TEXT NOT NULL DEFAULT 'product_api',
    ADD COLUMN IF NOT EXISTS source_record_id BIGINT,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;

UPDATE user_indicator_configs
SET symbol = UPPER(BTRIM(symbol))
WHERE symbol IS NOT NULL
  AND symbol <> UPPER(BTRIM(symbol));

UPDATE user_indicator_configs
SET category = LOWER(BTRIM(category))
WHERE category IS NOT NULL
  AND category <> LOWER(BTRIM(category));

CREATE UNIQUE INDEX IF NOT EXISTS ux_user_indicator_configs_canonical_asset_scope
ON user_indicator_configs (user_id, symbol, category, indicator)
WHERE symbol IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_user_indicator_configs_canonical_lookup
ON user_indicator_configs (user_id, symbol, category, enabled, priority, id)
WHERE symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS finn_v2_data_migration_audit (
    migration_id TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_count INTEGER NOT NULL,
    migrated_count INTEGER NOT NULL,
    ambiguous_count INTEGER NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (migration_id, source_table)
);

DO $$
DECLARE
    source_table_name TEXT;
    user_rule_count INTEGER;
    canonical_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO canonical_count
    FROM user_indicator_configs
    WHERE symbol IS NOT NULL;
    INSERT INTO finn_v2_data_migration_audit (
        migration_id, source_table, source_count, migrated_count, ambiguous_count
    ) VALUES (
        '2026_08_25_canonical_user_indicator_configs',
        'user_indicator_configs',
        canonical_count,
        canonical_count,
        (SELECT COUNT(*) FROM user_indicator_configs WHERE symbol IS NULL)
    )
    ON CONFLICT (migration_id, source_table) DO UPDATE
    SET source_count = EXCLUDED.source_count,
        migrated_count = EXCLUDED.migrated_count,
        ambiguous_count = EXCLUDED.ambiguous_count,
        recorded_at = CURRENT_TIMESTAMP;

    -- The legacy rule tables do not carry an asset symbol.  They are scoring
    -- rule definitions, not proof of an asset-specific user selection; do not
    -- invent a symbol while consolidating product state.
    FOREACH source_table_name IN ARRAY ARRAY[
        'technical_indicator_rules',
        'market_indicator_rules',
        'macro_indicator_rules'
    ]
    LOOP
        IF to_regclass(source_table_name) IS NULL THEN
            user_rule_count := 0;
        ELSE
            EXECUTE format('SELECT COUNT(*) FROM %I WHERE user_id IS NOT NULL', source_table_name)
            INTO user_rule_count;
        END IF;
        INSERT INTO finn_v2_data_migration_audit (
            migration_id, source_table, source_count, migrated_count, ambiguous_count
        ) VALUES (
            '2026_08_25_canonical_user_indicator_configs',
            source_table_name,
            user_rule_count,
            0,
            user_rule_count
        )
        ON CONFLICT (migration_id, source_table) DO UPDATE
        SET source_count = EXCLUDED.source_count,
            migrated_count = EXCLUDED.migrated_count,
            ambiguous_count = EXCLUDED.ambiguous_count,
            recorded_at = CURRENT_TIMESTAMP;
    END LOOP;
END $$;
"""


ROLLBACK_SQL = """
DROP INDEX IF EXISTS idx_user_indicator_configs_canonical_lookup;
DROP INDEX IF EXISTS ux_user_indicator_configs_canonical_asset_scope;
ALTER TABLE user_indicator_configs
    DROP COLUMN IF EXISTS updated_at,
    DROP COLUMN IF EXISTS source_record_id,
    DROP COLUMN IF EXISTS provenance,
    DROP COLUMN IF EXISTS config_json;
"""
