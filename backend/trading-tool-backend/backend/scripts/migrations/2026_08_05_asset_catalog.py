"""Create central asset catalog metadata table and seed core assets."""

SQL = """
CREATE TABLE IF NOT EXISTS asset_catalog (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR NOT NULL UNIQUE,
    display_name VARCHAR NOT NULL,
    asset_class VARCHAR NOT NULL DEFAULT 'crypto',
    logo_url VARCHAR,
    tradingview_symbol VARCHAR,
    coingecko_id VARCHAR,
    coincap_id VARCHAR,
    yahoo_symbol VARCHAR,
    provider VARCHAR DEFAULT 'manual',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_asset_catalog_symbol
ON asset_catalog (symbol);

CREATE INDEX IF NOT EXISTS idx_asset_catalog_asset_class
ON asset_catalog (asset_class);

CREATE INDEX IF NOT EXISTS idx_asset_catalog_is_active
ON asset_catalog (is_active);

INSERT INTO asset_catalog (
    symbol,
    display_name,
    asset_class,
    logo_url,
    tradingview_symbol,
    coingecko_id,
    coincap_id,
    yahoo_symbol,
    provider,
    is_active,
    metadata
) VALUES
    ('BTC', 'Bitcoin', 'crypto', 'https://assets.coincap.io/assets/icons/btc@2x.png', 'BINANCE:BTCUSDT', 'bitcoin', 'bitcoin', 'BTC-USD', 'seed', TRUE, '{"base_currency":"BTC","quote_currency":"USDT"}'::jsonb),
    ('ETH', 'Ethereum', 'crypto', 'https://assets.coincap.io/assets/icons/eth@2x.png', 'BINANCE:ETHUSDT', 'ethereum', 'ethereum', 'ETH-USD', 'seed', TRUE, '{"base_currency":"ETH","quote_currency":"USDT"}'::jsonb),
    ('SOL', 'Solana', 'crypto', 'https://assets.coincap.io/assets/icons/sol@2x.png', 'BINANCE:SOLUSDT', 'solana', 'solana', 'SOL-USD', 'seed', TRUE, '{"base_currency":"SOL","quote_currency":"USDT"}'::jsonb),
    ('SPY', 'SPDR S&P 500 ETF Trust', 'etf', NULL, 'AMEX:SPY', NULL, NULL, 'SPY', 'seed', TRUE, '{"exchange":"AMEX"}'::jsonb),
    ('QQQ', 'Invesco QQQ Trust', 'etf', NULL, 'NASDAQ:QQQ', NULL, NULL, 'QQQ', 'seed', TRUE, '{"exchange":"NASDAQ"}'::jsonb),
    ('AAPL', 'Apple Inc.', 'stock', NULL, 'NASDAQ:AAPL', NULL, NULL, 'AAPL', 'seed', TRUE, '{"exchange":"NASDAQ"}'::jsonb),
    ('MSFT', 'Microsoft Corporation', 'stock', NULL, 'NASDAQ:MSFT', NULL, NULL, 'MSFT', 'seed', TRUE, '{"exchange":"NASDAQ"}'::jsonb)
ON CONFLICT (symbol) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    asset_class = EXCLUDED.asset_class,
    logo_url = COALESCE(asset_catalog.logo_url, EXCLUDED.logo_url),
    tradingview_symbol = COALESCE(asset_catalog.tradingview_symbol, EXCLUDED.tradingview_symbol),
    coingecko_id = COALESCE(asset_catalog.coingecko_id, EXCLUDED.coingecko_id),
    coincap_id = COALESCE(asset_catalog.coincap_id, EXCLUDED.coincap_id),
    yahoo_symbol = COALESCE(asset_catalog.yahoo_symbol, EXCLUDED.yahoo_symbol),
    provider = COALESCE(asset_catalog.provider, EXCLUDED.provider),
    is_active = EXCLUDED.is_active,
    metadata = COALESCE(asset_catalog.metadata, EXCLUDED.metadata),
    updated_at = CURRENT_TIMESTAMP;
"""
