"""Reconcile legacy user indicator rules without inventing an asset scope."""

SQL = r"""
CREATE TABLE IF NOT EXISTS finn_v2_indicator_config_reconciliations (
    id BIGSERIAL PRIMARY KEY,
    source_key TEXT NOT NULL UNIQUE,
    source_table TEXT NOT NULL,
    source_user_id INTEGER NOT NULL,
    category TEXT NOT NULL,
    indicator TEXT NOT NULL,
    source_record_ids JSONB NOT NULL,
    legacy_config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'asset_scope_required'
        CHECK (status IN ('asset_scope_required', 'migrated', 'resolved')),
    resolved_symbol TEXT,
    canonical_config_id BIGINT REFERENCES user_indicator_configs(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_finn_v2_indicator_config_reconciliation_owner_status
ON finn_v2_indicator_config_reconciliations (source_user_id, status, category, indicator);

-- A symbol embedded in the historic payload is the only asset mapping that can
-- be migrated automatically.  The legacy scoring-rule tables themselves have
-- no asset column, so their rows remain explicit reconciliation work.
WITH legacy_scoped AS (
    SELECT
        id,
        user_id,
        LOWER(BTRIM(category)) AS category,
        LOWER(BTRIM(indicator)) AS indicator,
        UPPER(BTRIM(config_json ->> 'symbol')) AS symbol,
        config_json,
        COALESCE(priority, 100) AS priority,
        COALESCE(enabled, TRUE) AS enabled
    FROM user_indicator_configs
    WHERE symbol IS NULL
      AND NULLIF(BTRIM(config_json ->> 'symbol'), '') IS NOT NULL
), inserted AS (
    INSERT INTO user_indicator_configs (
        user_id, indicator, category, symbol, asset_class, priority, enabled,
        config_json, provenance, source_record_id
    )
    SELECT
        legacy.user_id,
        legacy.indicator,
        legacy.category,
        legacy.symbol,
        asset.asset_class,
        legacy.priority,
        legacy.enabled,
        legacy.config_json - 'symbol',
        'legacy_payload_migrated',
        legacy.id
    FROM legacy_scoped AS legacy
    JOIN asset_catalog AS asset ON UPPER(asset.symbol) = legacy.symbol
    ON CONFLICT (user_id, symbol, category, indicator) WHERE symbol IS NOT NULL
    DO NOTHING
    RETURNING id
)
INSERT INTO finn_v2_indicator_config_reconciliations (
    source_key, source_table, source_user_id, category, indicator,
    source_record_ids, legacy_config_json, status, resolved_symbol,
    canonical_config_id, resolved_at
)
SELECT
    'user_indicator_configs:' || legacy.id,
    'user_indicator_configs',
    legacy.user_id,
    legacy.category,
    legacy.indicator,
    jsonb_build_array(legacy.id),
    legacy.config_json,
    'migrated',
    legacy.symbol,
    canonical.id,
    CURRENT_TIMESTAMP
FROM legacy_scoped AS legacy
JOIN user_indicator_configs AS canonical
  ON canonical.user_id = legacy.user_id
 AND canonical.symbol = legacy.symbol
 AND canonical.category = legacy.category
 AND canonical.indicator = legacy.indicator
ON CONFLICT (source_key) DO UPDATE
SET status = 'migrated',
    resolved_symbol = EXCLUDED.resolved_symbol,
    canonical_config_id = EXCLUDED.canonical_config_id,
    resolved_at = COALESCE(finn_v2_indicator_config_reconciliations.resolved_at, CURRENT_TIMESTAMP),
    updated_at = CURRENT_TIMESTAMP;

DO $$
DECLARE
    source_table_name TEXT;
    category_name TEXT;
BEGIN
    FOR source_table_name, category_name IN
        SELECT * FROM (VALUES
            ('technical_indicator_rules', 'technical'),
            ('market_indicator_rules', 'market'),
            ('macro_indicator_rules', 'macro')
        ) AS sources(source_table_name, category_name)
    LOOP
        IF to_regclass(source_table_name) IS NOT NULL THEN
            EXECUTE format($statement$
                WITH grouped AS (
                    SELECT
                        %L || ':' || user_id || ':' || LOWER(BTRIM(indicator)) || ':' ||
                            COALESCE(LOWER(BTRIM(score_mode)), 'standard') || ':' ||
                            COALESCE(weight::TEXT, '1') || ':' || COALESCE(is_active::TEXT, 'true') AS source_key,
                        user_id,
                        LOWER(BTRIM(indicator)) AS indicator,
                        jsonb_agg(id ORDER BY id) AS source_record_ids,
                        jsonb_build_object(
                            'score_mode', COALESCE(MAX(score_mode), 'standard'),
                            'weight', COALESCE(MAX(weight), 1.0),
                            'enabled', COALESCE(BOOL_OR(is_active), TRUE),
                            'rules', jsonb_agg(
                                jsonb_build_object(
                                    'range_min', range_min,
                                    'range_max', range_max,
                                    'score', score,
                                    'trend', trend,
                                    'interpretation', interpretation,
                                    'action', action
                                ) ORDER BY id
                            )
                        ) AS legacy_config_json
                    FROM %I
                    WHERE user_id IS NOT NULL
                    GROUP BY user_id, LOWER(BTRIM(indicator)),
                             COALESCE(LOWER(BTRIM(score_mode)), 'standard'),
                             COALESCE(weight::TEXT, '1'), COALESCE(is_active::TEXT, 'true')
                )
                INSERT INTO finn_v2_indicator_config_reconciliations (
                    source_key, source_table, source_user_id, category, indicator,
                    source_record_ids, legacy_config_json, status
                )
                SELECT
                    source_key, %L, user_id, %L, indicator,
                    source_record_ids, legacy_config_json, 'asset_scope_required'
                FROM grouped
                ON CONFLICT (source_key) DO UPDATE
                SET source_record_ids = EXCLUDED.source_record_ids,
                    legacy_config_json = EXCLUDED.legacy_config_json,
                    updated_at = CURRENT_TIMESTAMP
                WHERE finn_v2_indicator_config_reconciliations.status = 'asset_scope_required'
            $statement$, source_table_name, source_table_name, source_table_name, category_name);
        END IF;
    END LOOP;
END $$;

-- Every historic unscoped config is visible either as a proven migration or as
-- an explicit asset_scope_required record.  No user selection is silently lost.
INSERT INTO finn_v2_indicator_config_reconciliations (
    source_key, source_table, source_user_id, category, indicator,
    source_record_ids, legacy_config_json, status
)
SELECT
    'user_indicator_configs:' || legacy.id,
    'user_indicator_configs',
    legacy.user_id,
    LOWER(BTRIM(legacy.category)),
    LOWER(BTRIM(legacy.indicator)),
    jsonb_build_array(legacy.id),
    legacy.config_json,
    'asset_scope_required'
FROM user_indicator_configs AS legacy
WHERE legacy.symbol IS NULL
ON CONFLICT (source_key) DO NOTHING;
"""

# Canonical records are intentionally retained on rollback.  Removing them
# would destroy user data after an otherwise successful reconciliation.
ROLLBACK_SQL = """
DROP INDEX IF EXISTS idx_finn_v2_indicator_config_reconciliation_owner_status;
DROP TABLE IF EXISTS finn_v2_indicator_config_reconciliations;
"""
