"""Switch macro indicators to the professional mixed-source macro stack."""

SQL = """
UPDATE indicators
SET display_name = 'US Dollar Index (Derived Basket)', source = 'derived', link = 'derived:dxy', active = TRUE
WHERE name = 'dxy';

UPDATE indicators
SET display_name = 'S&P 500 Index', source = 'fred', link = 'fred:SP500', active = TRUE
WHERE name = 'sp500';

UPDATE indicators
SET display_name = 'CBOE Volatility Index (VIX)', source = 'fred', link = 'fred:VIXCLS', active = TRUE
WHERE name = 'vix';

UPDATE indicators
SET source = 'twelve_data', link = 'twelve_data:XAU/USD', active = TRUE
WHERE name = 'gold_price';

UPDATE indicators
SET display_name = 'Crude Oil Price (WTI)', source = 'fred', link = 'fred:DCOILWTICO', active = TRUE
WHERE name = 'oil_price';

UPDATE indicators
SET display_name = 'US 10-Year Yield', source = 'fred', link = 'fred:DGS10', active = TRUE
WHERE name = 'us10y';

UPDATE indicators
SET display_name = 'US 2-Year Yield', source = 'fred', link = 'fred:DGS2', active = TRUE
WHERE name = 'us02y';

UPDATE indicators
SET source = 'fred', link = 'fred:FEDFUNDS', active = TRUE
WHERE name = 'interest_rate';

UPDATE indicators
SET source = 'fred', link = 'fred:CPIAUCSL', active = TRUE
WHERE name = 'inflation_rate';

UPDATE indicators
SET source = 'custom', link = 'https://trends.google.com/trends/api/widgetdata/multiline', active = FALSE
WHERE name = 'google_trends';

UPDATE indicators
SET source = 'custom', link = 'https://bitbo.io/treasuries/etf-flows/', active = TRUE
WHERE name = 'etf_bitcoin_inflow';
"""
