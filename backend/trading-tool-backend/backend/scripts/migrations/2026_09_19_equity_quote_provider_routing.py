"""Make the supported AAPL/MSFT quote route explicit and idempotent."""

SQL = """
UPDATE asset_catalog
SET
    provider = 'twelve_data',
    primary_provider = 'twelve_data',
    provider_symbol = symbol,
    exchange = 'NASDAQ',
    market_region = 'us',
    timezone = 'America/New_York',
    quote_currency = 'USD',
    refresh_policy = 'securities_live_5m',
    updated_at = CURRENT_TIMESTAMP
WHERE symbol IN ('AAPL', 'MSFT');
"""
