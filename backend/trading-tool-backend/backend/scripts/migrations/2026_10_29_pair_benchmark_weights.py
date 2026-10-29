"""Keep category weights with the exact market being analysed or traded."""

SQL = """
CREATE TABLE IF NOT EXISTS user_market_benchmark_weights (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    market_id BIGINT NOT NULL REFERENCES trading_markets(id) ON DELETE CASCADE,
    weights JSONB NOT NULL,
    indicators_isolated BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, market_id)
);

ALTER TABLE user_market_benchmark_weights
ADD COLUMN IF NOT EXISTS indicators_isolated BOOLEAN NOT NULL DEFAULT FALSE;

INSERT INTO user_market_benchmark_weights(user_id, market_id, weights)
SELECT scopes.user_id, scopes.market_id,
       COALESCE(u.ai_preferences::jsonb->'intelligence_weights',
                '{"market":0.333333333333,"macro":0.333333333333,"technical":0.333333333334}'::jsonb)
FROM (
    SELECT DISTINCT user_id, market_id FROM user_indicator_configs WHERE market_id IS NOT NULL
    UNION
    SELECT DISTINCT user_id, market_id FROM setups WHERE market_id IS NOT NULL
    UNION
    SELECT DISTINCT w.user_id, m.id FROM watchlists w
    JOIN trading_markets m ON m.asset_symbol = w.symbol AND m.is_active = TRUE
) scopes
JOIN users u ON u.id = scopes.user_id
ON CONFLICT (user_id, market_id) DO NOTHING;
"""
