"""Extend asset_catalog with provider-routing fields and seed V1 multi-asset coverage."""

SQL = """
ALTER TABLE asset_catalog
ADD COLUMN IF NOT EXISTS primary_provider VARCHAR,
ADD COLUMN IF NOT EXISTS fallback_provider VARCHAR,
ADD COLUMN IF NOT EXISTS provider_symbol VARCHAR,
ADD COLUMN IF NOT EXISTS exchange VARCHAR,
ADD COLUMN IF NOT EXISTS market_region VARCHAR,
ADD COLUMN IF NOT EXISTS timezone VARCHAR,
ADD COLUMN IF NOT EXISTS base_currency VARCHAR,
ADD COLUMN IF NOT EXISTS quote_currency VARCHAR,
ADD COLUMN IF NOT EXISTS entitlement_tier VARCHAR DEFAULT 'internal',
ADD COLUMN IF NOT EXISTS is_delayed BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS refresh_policy VARCHAR;

UPDATE asset_catalog
SET
    primary_provider = COALESCE(primary_provider, provider, 'manual'),
    provider_symbol = COALESCE(provider_symbol, symbol),
    timezone = COALESCE(timezone, 'UTC'),
    market_region = COALESCE(market_region, 'global'),
    entitlement_tier = COALESCE(entitlement_tier, 'internal')
WHERE
    primary_provider IS NULL
    OR provider_symbol IS NULL
    OR timezone IS NULL
    OR market_region IS NULL
    OR entitlement_tier IS NULL;

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
    primary_provider,
    fallback_provider,
    provider_symbol,
    exchange,
    market_region,
    timezone,
    base_currency,
    quote_currency,
    entitlement_tier,
    is_delayed,
    refresh_policy,
    is_active,
    metadata
) VALUES
    ('BTC', 'Bitcoin', 'crypto', 'https://assets.coincap.io/assets/icons/btc@2x.png', 'BINANCE:BTCUSDT', 'bitcoin', 'bitcoin', 'BTC-USD', 'binance', 'binance', NULL, 'BTCUSDT', 'BINANCE', 'global', 'UTC', 'BTC', 'USDT', 'internal', FALSE, 'crypto_live_1m', TRUE, '{"provider_family":"exchange","asset_role":"core"}'::jsonb),
    ('ETH', 'Ethereum', 'crypto', 'https://assets.coincap.io/assets/icons/eth@2x.png', 'BINANCE:ETHUSDT', 'ethereum', 'ethereum', 'ETH-USD', 'binance', 'binance', NULL, 'ETHUSDT', 'BINANCE', 'global', 'UTC', 'ETH', 'USDT', 'internal', FALSE, 'crypto_live_1m', TRUE, '{"provider_family":"exchange","asset_role":"core"}'::jsonb),
    ('SOL', 'Solana', 'crypto', 'https://assets.coincap.io/assets/icons/sol@2x.png', 'BINANCE:SOLUSDT', 'solana', 'solana', 'SOL-USD', 'binance', 'binance', NULL, 'SOLUSDT', 'BINANCE', 'global', 'UTC', 'SOL', 'USDT', 'internal', FALSE, 'crypto_live_1m', TRUE, '{"provider_family":"exchange","asset_role":"core"}'::jsonb),
    ('XRP', 'XRP', 'crypto', 'https://assets.coincap.io/assets/icons/xrp@2x.png', 'BINANCE:XRPUSDT', NULL, NULL, 'XRP-USD', 'binance', 'binance', NULL, 'XRPUSDT', 'BINANCE', 'global', 'UTC', 'XRP', 'USDT', 'internal', FALSE, 'crypto_live_1m', TRUE, '{"provider_family":"exchange","asset_role":"core"}'::jsonb),
    ('LINK', 'Chainlink', 'crypto', 'https://assets.coincap.io/assets/icons/link@2x.png', 'BINANCE:LINKUSDT', NULL, NULL, 'LINK-USD', 'binance', 'binance', NULL, 'LINKUSDT', 'BINANCE', 'global', 'UTC', 'LINK', 'USDT', 'internal', FALSE, 'crypto_live_1m', TRUE, '{"provider_family":"exchange","asset_role":"core"}'::jsonb),
    ('MSTR', 'Strategy Inc.', 'stock', NULL, 'NASDAQ:MSTR', NULL, NULL, 'MSTR', 'twelve_data', 'twelve_data', NULL, 'MSTR', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('COIN', 'Coinbase Global, Inc.', 'stock', NULL, 'NASDAQ:COIN', NULL, NULL, 'COIN', 'twelve_data', 'twelve_data', NULL, 'COIN', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('MARA', 'MARA Holdings, Inc.', 'stock', NULL, 'NASDAQ:MARA', NULL, NULL, 'MARA', 'twelve_data', 'twelve_data', NULL, 'MARA', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('RIOT', 'Riot Platforms, Inc.', 'stock', NULL, 'NASDAQ:RIOT', NULL, NULL, 'RIOT', 'twelve_data', 'twelve_data', NULL, 'RIOT', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('CLSK', 'CleanSpark, Inc.', 'stock', NULL, 'NASDAQ:CLSK', NULL, NULL, 'CLSK', 'twelve_data', 'twelve_data', NULL, 'CLSK', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('HUT', 'Hut 8 Corp.', 'stock', NULL, 'NASDAQ:HUT', NULL, NULL, 'HUT', 'twelve_data', 'twelve_data', NULL, 'HUT', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('BTDR', 'Bitdeer Technologies Group', 'stock', NULL, 'NASDAQ:BTDR', NULL, NULL, 'BTDR', 'twelve_data', 'twelve_data', NULL, 'BTDR', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('WULF', 'TeraWulf Inc.', 'stock', NULL, 'NASDAQ:WULF', NULL, NULL, 'WULF', 'twelve_data', 'twelve_data', NULL, 'WULF', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('CORZ', 'Core Scientific, Inc.', 'stock', NULL, 'NASDAQ:CORZ', NULL, NULL, 'CORZ', 'twelve_data', 'twelve_data', NULL, 'CORZ', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_equity"}'::jsonb),
    ('SPY', 'SPDR S&P 500 ETF Trust', 'etf', NULL, 'AMEX:SPY', NULL, NULL, 'SPY', 'twelve_data', 'twelve_data', NULL, 'SPY', 'AMEX', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_proxy"}'::jsonb),
    ('QQQ', 'Invesco QQQ Trust', 'etf', NULL, 'NASDAQ:QQQ', NULL, NULL, 'QQQ', 'twelve_data', 'twelve_data', NULL, 'QQQ', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_proxy"}'::jsonb),
    ('IBIT', 'iShares Bitcoin Trust ETF', 'etf', NULL, 'NASDAQ:IBIT', NULL, NULL, 'IBIT', 'twelve_data', 'twelve_data', NULL, 'IBIT', 'NASDAQ', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_etf"}'::jsonb),
    ('FBTC', 'Fidelity Wise Origin Bitcoin Fund', 'etf', NULL, 'AMEX:FBTC', NULL, NULL, 'FBTC', 'twelve_data', 'twelve_data', NULL, 'FBTC', 'AMEX', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"crypto_etf"}'::jsonb),
    ('GLD', 'SPDR Gold Shares', 'etf', NULL, 'AMEX:GLD', NULL, NULL, 'GLD', 'twelve_data', 'twelve_data', NULL, 'GLD', 'AMEX', 'us', 'America/New_York', NULL, 'USD', 'internal', FALSE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_proxy"}'::jsonb),
    ('SPX', 'S&P 500 Index', 'index', NULL, 'SP:SPX', NULL, NULL, '^GSPC', 'twelve_data', 'twelve_data', NULL, 'SPX', 'INDEX', 'us', 'America/New_York', NULL, 'USD', 'internal', TRUE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_index"}'::jsonb),
    ('NDX', 'Nasdaq-100 Index', 'index', NULL, 'NASDAQ:NDX', NULL, NULL, '^NDX', 'twelve_data', 'twelve_data', NULL, 'NDX', 'INDEX', 'us', 'America/New_York', NULL, 'USD', 'internal', TRUE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_index"}'::jsonb),
    ('VIX', 'CBOE Volatility Index', 'index', NULL, 'CBOE:VIX', NULL, NULL, '^VIX', 'twelve_data', 'twelve_data', NULL, 'VIX', 'CBOE', 'us', 'America/New_York', NULL, 'USD', 'internal', TRUE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_index"}'::jsonb),
    ('DXY', 'US Dollar Index', 'index', NULL, 'TVC:DXY', NULL, NULL, 'DX-Y.NYB', 'twelve_data', 'twelve_data', NULL, 'DXY', 'ICE', 'us', 'America/New_York', NULL, 'USD', 'internal', TRUE, 'securities_live_5m', TRUE, '{"provider_family":"securities","asset_role":"macro_index"}'::jsonb)
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
    primary_provider = COALESCE(asset_catalog.primary_provider, EXCLUDED.primary_provider),
    fallback_provider = COALESCE(asset_catalog.fallback_provider, EXCLUDED.fallback_provider),
    provider_symbol = COALESCE(asset_catalog.provider_symbol, EXCLUDED.provider_symbol),
    exchange = COALESCE(asset_catalog.exchange, EXCLUDED.exchange),
    market_region = COALESCE(asset_catalog.market_region, EXCLUDED.market_region),
    timezone = COALESCE(asset_catalog.timezone, EXCLUDED.timezone),
    base_currency = COALESCE(asset_catalog.base_currency, EXCLUDED.base_currency),
    quote_currency = COALESCE(asset_catalog.quote_currency, EXCLUDED.quote_currency),
    entitlement_tier = COALESCE(asset_catalog.entitlement_tier, EXCLUDED.entitlement_tier),
    is_delayed = COALESCE(asset_catalog.is_delayed, EXCLUDED.is_delayed),
    refresh_policy = COALESCE(asset_catalog.refresh_policy, EXCLUDED.refresh_policy),
    is_active = EXCLUDED.is_active,
    metadata = COALESCE(asset_catalog.metadata, EXCLUDED.metadata),
    updated_at = CURRENT_TIMESTAMP;
"""
