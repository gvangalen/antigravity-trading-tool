"""Install explicit, descriptive rules for the default Score 2.0 indicators.

The rules describe measured position or momentum. They are not trade signals.
Existing global buckets and owner-specific custom curves are preserved.
"""

SQL = """
INSERT INTO market_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'price', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 30, 'laag', 'Prijs ligt laag in het eigen recente 30-daagse bereik; dit meet relatieve prijspositie, geen koopsignaal.'),
    (20, 40, 40, 'onder midden', 'Prijs ligt onder het midden van het eigen recente 30-daagse bereik; dit meet relatieve prijspositie.'),
    (40, 60, 50, 'midden', 'Prijs ligt rond het midden van het eigen recente 30-daagse bereik; dit meet relatieve prijspositie.'),
    (60, 80, 60, 'boven midden', 'Prijs ligt boven het midden van het eigen recente 30-daagse bereik; dit meet relatieve prijspositie.'),
    (80, 100, 80, 'hoog', 'Prijs ligt hoog in het eigen recente 30-daagse bereik; dit meet relatieve prijspositie, geen instapbevestiging.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM market_indicator_rules existing
    WHERE existing.indicator = 'price' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

-- Volume is measured participation, not bullish direction. Its standard
-- contribution cannot on its own create a strongly positive market score.
INSERT INTO market_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'volume', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van handelsvolume alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 20, 'zeer laag volume', 'Handelsvolume is zeer laag ten opzichte van de recente mediaan; dit meet activiteit, geen richting.'),
    (20, 40, 30, 'laag volume', 'Handelsvolume is laag ten opzichte van de recente mediaan; dit meet activiteit, geen richting.'),
    (40, 60, 40, 'gebruikelijk volume', 'Handelsvolume ligt rond de recente mediaan; dit meet activiteit, geen richting.'),
    (60, 80, 50, 'hoger volume', 'Handelsvolume ligt boven de recente mediaan; dit bevestigt op zichzelf geen stijgende markt.'),
    (80, 100, 50, 'zeer hoog volume', 'Handelsvolume is sterk verhoogd; zonder prijsrichting volgt hieruit geen koop- of verkoopsignaal.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM market_indicator_rules existing
    WHERE existing.indicator = 'volume' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

INSERT INTO market_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'change_24h', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van een koersverandering alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 20, 'sterk negatief', 'De 24-uurs koersverandering is sterk negatief; dit beschrijft korte-termijn richting, geen voorspelling.'),
    (20, 40, 35, 'negatief', 'De 24-uurs koersverandering is negatief; dit beschrijft korte-termijn richting.'),
    (40, 60, 50, 'gemengd', 'De 24-uurs koersverandering ligt rond nul; dit is geen instapbevestiging.'),
    (60, 80, 65, 'positief', 'De 24-uurs koersverandering is positief; dit is geen instapbevestiging.'),
    (80, 100, 80, 'sterk positief', 'De 24-uurs koersverandering is sterk positief; dit is geen zelfstandig instapsignaal.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM market_indicator_rules existing
    WHERE existing.indicator = 'change_24h' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

INSERT INTO macro_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'dxy', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 80, 'lage dollarsterkte', 'DXY ligt laag in het eigen recente 90-daagse bereik; dit model ziet dat als gunstiger algemeen risicoklimaat.'),
    (20, 40, 60, 'lagere dollarsterkte', 'DXY ligt onder het midden van het eigen recente 90-daagse bereik; dit is macrocontext, geen assetsignaal.'),
    (40, 60, 50, 'midden', 'DXY ligt rond het midden van het eigen recente 90-daagse bereik; dit is neutrale macrocontext.'),
    (60, 80, 40, 'hogere dollarsterkte', 'DXY ligt boven het midden van het eigen recente 90-daagse bereik; dit model ziet dat als voorzichtiger algemeen risicoklimaat.'),
    (80, 100, 20, 'hoge dollarsterkte', 'DXY ligt hoog in het eigen recente 90-daagse bereik; dit is macrocontext, geen verkoopadvies.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM macro_indicator_rules existing
    WHERE existing.indicator = 'dxy' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);

INSERT INTO technical_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT 'rsi', bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    (0, 20, 30, 'zeer laag momentum', 'RSI is zeer laag; dit geeft momentumcontext, niet automatisch een koopkans.'),
    (20, 40, 40, 'laag momentum', 'RSI is laag; dit geeft momentumcontext, niet automatisch een koopkans.'),
    (40, 60, 50, 'gemengd momentum', 'RSI ligt in de middenzone; een aparte entrybevestiging is hiermee niet bewezen.'),
    (60, 80, 80, 'sterker momentum', 'RSI wijst op sterker momentum; dit is geen zelfstandige instapbevestiging.'),
    (80, 100, 45, 'hoog momentum', 'RSI is zeer hoog en kan overstrekt zijn; dit is geen zelfstandig verkoopsignaal.')
) AS bucket(range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM technical_indicator_rules existing
    WHERE existing.indicator = 'rsi' AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min AND existing.range_max = bucket.range_max
);
"""
