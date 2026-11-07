"""Complete the standard Score 2.0 curves for every active catalog indicator.

These buckets receive normalized 0–100 measurements. Existing system and
owner curves are preserved so a deployment cannot overwrite user choices.
"""

SQL = """
INSERT INTO macro_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT template.indicator, bucket.range_min, bucket.range_max,
       CASE WHEN template.direction = 'inverse' THEN bucket.inverse_score
            ELSE bucket.forward_score END,
       bucket.trend,
       template.description || ' ' || bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    ('etf_bitcoin_inflow', 'forward', 'Netto instroom in Amerikaanse spot-Bitcoin-ETF’s, in miljoenen USD.'),
    ('oil_price', 'inverse', 'WTI-olieprijs vergeleken met het eigen recente 90-daagse bereik.'),
    ('us10y', 'inverse', 'Rendement op Amerikaanse staatsobligaties met een looptijd van 10 jaar.'),
    ('us02y', 'inverse', 'Rendement op Amerikaanse staatsobligaties met een looptijd van 2 jaar.'),
    ('interest_rate', 'inverse', 'Amerikaanse beleidsrente.'),
    ('inflation_rate', 'inverse', 'Amerikaanse CPI-inflatie op jaarbasis.')
) AS template(indicator, direction, description)
CROSS JOIN (VALUES
    (0, 20, 20, 80, 'zeer laag', 'De meting ligt in de laagste zone; dit is macrocontext, geen zelfstandig assetsignaal.'),
    (20, 40, 35, 65, 'laag', 'De meting ligt onder het midden van het gekozen bereik.'),
    (40, 60, 50, 50, 'gemengd', 'De meting ligt rond het midden van het gekozen bereik.'),
    (60, 80, 65, 35, 'hoog', 'De meting ligt boven het midden van het gekozen bereik.'),
    (80, 100, 80, 20, 'zeer hoog', 'De meting ligt in de hoogste zone; dit is geen zelfstandig handelssignaal.')
) AS bucket(range_min, range_max, forward_score, inverse_score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM macro_indicator_rules existing
    WHERE existing.indicator = template.indicator AND existing.user_id IS NULL
      AND existing.is_active = TRUE
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

INSERT INTO technical_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT template.indicator, bucket.range_min, bucket.range_max,
       CASE WHEN template.indicator = 'atr_pct' THEN bucket.volatility_score
            WHEN template.indicator = 'adx' THEN bucket.trend_score
            ELSE bucket.directional_score END,
       bucket.trend, template.description || ' ' || bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    ('adx', 'ADX meet trendsterkte, niet de richting.'),
    ('atr_pct', 'ATR als percentage van de koers meet volatiliteit, niet de richting.'),
    ('ema_20_gap_pct', 'Koersafstand tot EMA 20 als percentage van de koers.'),
    ('ema_50_gap_pct', 'Koersafstand tot EMA 50 als percentage van de koers.')
) AS template(indicator, description)
CROSS JOIN (VALUES
    (0, 20, 20, 70, 20, 'zeer laag', 'De genormaliseerde meting ligt in de laagste zone.'),
    (20, 40, 35, 60, 35, 'laag', 'De genormaliseerde meting ligt in een lage zone.'),
    (40, 60, 50, 50, 50, 'gemengd', 'De genormaliseerde meting ligt rond het midden.'),
    (60, 80, 65, 35, 60, 'hoog', 'De genormaliseerde meting ligt in een hoge zone.'),
    (80, 100, 75, 20, 65, 'zeer hoog', 'De genormaliseerde meting ligt in de hoogste zone.')
) AS bucket(range_min, range_max, directional_score, volatility_score, trend_score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM technical_indicator_rules existing
    WHERE existing.indicator = template.indicator AND existing.user_id IS NULL
      AND existing.is_active = TRUE
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);
"""
