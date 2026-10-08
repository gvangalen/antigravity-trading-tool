"""Archive derived-basket DXY measurements before using the direct index series.

The old and new sources have different values. Keeping the old rows under a
distinct historical name prevents mixed-source normalization while retaining
the original observations for audit and rollback.
"""

SQL = """
UPDATE indicators
SET display_name = 'US Dollar Index (DXY)', source = 'yahoo',
    link = 'https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB', active = TRUE
WHERE name = 'dxy';

CREATE TABLE IF NOT EXISTS score_source_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM score_source_migrations WHERE name = 'dxy_direct_index_v1'
    ) THEN
        UPDATE macro_data
        SET name = 'dxy_derived_legacy', score = NULL
        WHERE LOWER(name) = 'dxy';

        UPDATE daily_scores
        SET macro_score = NULL, setup_score = NULL,
            indicator_evidence = NULL, calculated_at = NULL
        WHERE report_date >= CURRENT_DATE - INTERVAL '4 days'
          AND user_id IN (
              SELECT DISTINCT user_id FROM user_indicator_configs
              WHERE category = 'macro' AND LOWER(indicator) = 'dxy'
          );

        INSERT INTO score_source_migrations (name) VALUES ('dxy_direct_index_v1');
    END IF;
END $$;
"""

ROLLBACK_SQL = """
UPDATE indicators
SET display_name = 'US Dollar Index (Derived Basket)', source = 'derived',
    link = 'derived:dxy'
WHERE name = 'dxy';
UPDATE macro_data SET name = 'dxy'
WHERE name = 'dxy_derived_legacy';
DELETE FROM score_source_migrations WHERE name = 'dxy_direct_index_v1';
"""
