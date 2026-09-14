"""Make Strategy an owner-scoped child domain instead of a setup singleton."""

SQL = """
ALTER TABLE strategies
    ADD COLUMN IF NOT EXISTS canonical_name VARCHAR,
    ADD COLUMN IF NOT EXISTS symbol VARCHAR,
    ADD COLUMN IF NOT EXISTS timeframe VARCHAR;

UPDATE strategies AS strategy
SET
    canonical_name = COALESCE(
        strategy.canonical_name,
        NULLIF(lower(trim(strategy.name)), ''),
        concat('legacy-strategy-', strategy.id)
    ),
    symbol = COALESCE(
        strategy.symbol,
        NULLIF(strategy.data->>'symbol', ''),
        setup.symbol
    ),
    timeframe = COALESCE(
        strategy.timeframe,
        NULLIF(strategy.data->>'timeframe', ''),
        setup.timeframe
    )
FROM setups AS setup
WHERE setup.id = strategy.setup_id;

CREATE UNIQUE INDEX IF NOT EXISTS strategies_owner_setup_canonical_name_uq
    ON strategies (user_id, setup_id, canonical_name)
    WHERE canonical_name IS NOT NULL;

CREATE INDEX IF NOT EXISTS strategies_owner_setup_created_idx
    ON strategies (user_id, setup_id, created_at DESC);
"""
