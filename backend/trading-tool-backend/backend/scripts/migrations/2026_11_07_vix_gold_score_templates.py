"""Install complete default buckets for selectable VIX and gold indicators.

VIX uses its normalized volatility reading; calmer conditions score higher.
Gold uses its position in the owner's dated 90-day range. Its score describes
gold strength as macro context, not a trading instruction. Existing system
buckets and owner-specific curves are preserved.
"""

SQL = """
INSERT INTO macro_indicator_rules
    (indicator, range_min, range_max, score, trend, interpretation, action,
     score_mode, weight, is_active, user_id)
SELECT bucket.indicator, bucket.range_min, bucket.range_max, bucket.score,
       bucket.trend, bucket.interpretation,
       'Geen handelsactie op basis van deze indicator alleen.',
       'standard', 1.0, TRUE, NULL
FROM (VALUES
    ('vix', 0, 20, 80, 'rustige volatiliteit', 'VIX is laag; dit wijst op rustiger marktomstandigheden, niet op een zelfstandig instapsignaal.'),
    ('vix', 20, 40, 65, 'beperkte volatiliteit', 'VIX wijst op beperkte volatiliteit; dit is algemene risicocontext.'),
    ('vix', 40, 60, 50, 'gemengde volatiliteit', 'VIX ligt in een gemengde zone; de volatiliteit geeft geen duidelijke bevestiging.'),
    ('vix', 60, 80, 35, 'verhoogde volatiliteit', 'VIX is verhoogd; het algemene risicoklimaat vraagt meer voorzichtigheid.'),
    ('vix', 80, 100, 20, 'hoge volatiliteit', 'VIX is hoog; dit duidt op marktstress, niet op een zelfstandig verkoopsignaal.'),
    ('gold_price', 0, 20, 20, 'zwakke goudprijs', 'Goud ligt laag in het eigen recente 90-daagse bereik; dit beschrijft goudsterkte, geen assetsignaal.'),
    ('gold_price', 20, 40, 35, 'lagere goudprijs', 'Goud ligt onder het midden van het eigen recente 90-daagse bereik; dit is macrocontext.'),
    ('gold_price', 40, 60, 50, 'gemengde goudprijs', 'Goud ligt rond het midden van het eigen recente 90-daagse bereik; dit is neutrale macrocontext.'),
    ('gold_price', 60, 80, 65, 'sterkere goudprijs', 'Goud ligt boven het midden van het eigen recente 90-daagse bereik; dit is geen zelfstandig handelssignaal.'),
    ('gold_price', 80, 100, 80, 'sterke goudprijs', 'Goud ligt hoog in het eigen recente 90-daagse bereik; dit kan ook vraag naar bescherming weerspiegelen en is geen instapbevestiging.')
) AS bucket(indicator, range_min, range_max, score, trend, interpretation)
WHERE NOT EXISTS (
    SELECT 1 FROM macro_indicator_rules existing
    WHERE existing.indicator = bucket.indicator AND existing.user_id IS NULL
      AND existing.range_min = bucket.range_min
      AND existing.range_max = bucket.range_max
);
"""
