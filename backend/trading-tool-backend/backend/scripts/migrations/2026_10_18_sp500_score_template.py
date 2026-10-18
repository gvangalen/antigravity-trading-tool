"""Supply an explicit score rule for the selectable S&P 500 macro indicator.

The input is its position in the owner's dated 90-day range, not the raw
index level. Existing template buckets and owner curves are left intact.
"""

SQL = """
INSERT INTO macro_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'sp500', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 20, 'lage aandelenmarkt', 'S&P 500 ligt laag in het eigen recente 90-daagse bereik; dit is macrocontext, geen koopsignaal.'),
    (20, 40, 35, 'zwakkere aandelenmarkt', 'S&P 500 ligt onder het midden van het eigen recente 90-daagse bereik; dit is macrocontext.'),
    (40, 60, 50, 'gemengde aandelenmarkt', 'S&P 500 ligt rond het midden van het eigen recente 90-daagse bereik; dit is macrocontext.'),
    (60, 80, 65, 'sterkere aandelenmarkt', 'S&P 500 ligt boven het midden van het eigen recente 90-daagse bereik; dit is macrocontext, geen instapbevestiging.'),
    (80, 100, 80, 'hoge aandelenmarkt', 'S&P 500 ligt hoog in het eigen recente 90-daagse bereik; dit is macrocontext, geen zelfstandig handelssignaal.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM macro_indicator_rules existing
    WHERE existing.indicator = 'sp500' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);
"""
