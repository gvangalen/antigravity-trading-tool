"""Install explicit Score 2.0 rules for supported MA50 and MACD readings.

The input to these buckets is a normalized, directional measurement. Existing
owner curves and existing system buckets are preserved.
"""

SQL = """
INSERT INTO technical_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT template.indicator, bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       NULL,
       'standard', 1.0, TRUE, NULL
FROM (VALUES ('ma_50'), ('macd_hist_pct')) AS template(indicator)
CROSS JOIN (VALUES
    (0, 20, 20, 'sterk negatief', 'De meting ligt ruim onder de neutrale lijn.'),
    (20, 40, 35, 'negatief', 'De meting ligt onder de neutrale lijn.'),
    (40, 60, 50, 'neutraal', 'De meting ligt rond de neutrale lijn.'),
    (60, 80, 65, 'positief', 'De meting ligt boven de neutrale lijn.'),
    (80, 100, 75, 'sterk positief', 'De meting ligt ruim boven de neutrale lijn.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM technical_indicator_rules existing
    WHERE existing.indicator = template.indicator AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min
      AND existing.range_max = bucket.range_max
);
"""
