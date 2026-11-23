"""Calibrate standard RSI momentum scores to the selected 12..90 range.

The five stored buckets describe normalized position, not raw RSI. Owner
custom curves remain unchanged. A low RSI is weak momentum, never a buy cue.
"""

SQL = """
CREATE TABLE IF NOT EXISTS score_source_migrations (
    name TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
DO $$
BEGIN
IF NOT EXISTS (
    SELECT 1 FROM score_source_migrations WHERE name = 'rsi_momentum_12_90_v1'
) THEN
UPDATE technical_indicator_rules AS existing
SET score = bucket.score,
    trend = bucket.trend,
    interpretation = bucket.interpretation,
    action = 'Geen handelsactie op basis van deze indicator alleen.'
FROM (VALUES
    (0, 20, 0, 'zeer zwak momentum', 'RSI ligt in de laagste momentumzone; dit is geen zelfstandig koopsignaal.'),
    (20, 40, 25, 'zwak momentum', 'RSI wijst op zwak momentum; een herstel is nog niet bevestigd.'),
    (40, 60, 50, 'gemengd momentum', 'RSI ligt in de middenzone; de richting is niet bevestigd.'),
    (60, 80, 75, 'sterker momentum', 'RSI wijst op sterker momentum; dit is geen zelfstandige instapbevestiging.'),
    (80, 100, 100, 'zeer sterk momentum', 'RSI is hoog; momentum is sterk maar kan overstrekt zijn.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE existing.indicator = 'rsi' AND existing.user_id IS NULL
  AND existing.range_min = bucket.range_min
  AND existing.range_max = bucket.range_max;

INSERT INTO technical_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'rsi', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 0, 'zeer zwak momentum', 'RSI ligt in de laagste momentumzone; dit is geen zelfstandig koopsignaal.'),
    (20, 40, 25, 'zwak momentum', 'RSI wijst op zwak momentum; een herstel is nog niet bevestigd.'),
    (40, 60, 50, 'gemengd momentum', 'RSI ligt in de middenzone; de richting is niet bevestigd.'),
    (60, 80, 75, 'sterker momentum', 'RSI wijst op sterker momentum; dit is geen zelfstandige instapbevestiging.'),
    (80, 100, 100, 'zeer sterk momentum', 'RSI is hoog; momentum is sterk maar kan overstrekt zijn.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM technical_indicator_rules existing
    WHERE existing.indicator = 'rsi' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

-- The previous RSI score was computed on raw 0..100 and must not remain a
-- current decision input after the rule and normalization change. Preserve
-- dated measurements and historical rows; the regular score worker rebuilds
-- current evidence from the same completed candles.
UPDATE technical_indicators AS reading
SET score = NULL, advies = NULL, uitleg = NULL
WHERE reading.indicator = 'rsi'
  AND reading.source_observed_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - 3
  AND EXISTS (
      SELECT 1 FROM daily_scores AS daily
      WHERE daily.user_id = reading.user_id
        AND daily.symbol = reading.symbol
        AND daily.market_id IS NOT DISTINCT FROM reading.market_id
        AND daily.report_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - 2
        AND daily.indicator_evidence #>> '{technical,rsi,mode}' IN ('standard', 'contrarian')
  );

UPDATE daily_scores AS daily
SET technical_score = NULL,
    indicator_evidence = (daily.indicator_evidence::jsonb #- '{technical,rsi}')::jsonb
WHERE daily.report_date >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date - 2
  AND daily.indicator_evidence #>> '{technical,rsi,mode}' IN ('standard', 'contrarian');

INSERT INTO score_source_migrations (name) VALUES ('rsi_momentum_12_90_v1');
END IF;
END $$;
"""
