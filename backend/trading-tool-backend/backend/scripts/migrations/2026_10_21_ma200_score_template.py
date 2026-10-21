"""Score the close-to-MA200 ratio without mistaking below for above.

The normalized input is 0 at or below 0.8 times MA200, 50 at MA200,
and 100 at or above 1.2 times MA200. Owner rules are never replaced.
"""

SQL = """
INSERT INTO technical_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'ma_200', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 20, 'ruim onder MA200', 'De prijs ligt ruim onder het 200-daags gemiddelde; de langetermijntrend is zwak.'),
    (20, 40, 35, 'onder MA200', 'De prijs ligt onder het 200-daags gemiddelde; de langetermijntrend geeft weinig steun.'),
    (40, 60, 50, 'rond MA200', 'De prijs ligt rond het 200-daags gemiddelde; dit geeft geen duidelijke richting.'),
    (60, 80, 65, 'boven MA200', 'De prijs ligt boven het 200-daags gemiddelde; dit ondersteunt de langetermijntrend.'),
    (80, 100, 75, 'ruim boven MA200', 'De prijs ligt ruim boven het 200-daags gemiddelde; de trend is sterk maar kan uitgerekt zijn.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM technical_indicator_rules existing
    WHERE existing.indicator = 'ma_200' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);
"""
