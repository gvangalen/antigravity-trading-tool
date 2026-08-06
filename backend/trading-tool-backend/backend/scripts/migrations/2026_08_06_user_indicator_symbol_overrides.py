"""Add symbol-aware user indicator config overrides."""

SQL = """
ALTER TABLE user_indicator_configs
ADD COLUMN IF NOT EXISTS symbol VARCHAR,
ADD COLUMN IF NOT EXISTS asset_class VARCHAR,
ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100,
ADD COLUMN IF NOT EXISTS enabled BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_user_indicator_configs_user_category_symbol
ON user_indicator_configs (user_id, category, symbol);

CREATE INDEX IF NOT EXISTS idx_user_indicator_configs_user_category_asset_class
ON user_indicator_configs (user_id, category, asset_class);

CREATE UNIQUE INDEX IF NOT EXISTS ux_user_indicator_configs_scope
ON user_indicator_configs (
    user_id,
    category,
    indicator,
    COALESCE(symbol, ''),
    COALESCE(asset_class, '')
);
"""
