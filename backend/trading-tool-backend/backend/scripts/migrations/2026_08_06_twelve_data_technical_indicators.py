"""Seed Twelve Data-backed technical indicators and default scoring rules."""

SQL = """
INSERT INTO indicators (name, display_name, category, source, link, active)
VALUES
    ('ema_20_gap_pct', 'EMA20 Gap %', 'technical', 'twelve_data', 'twelve_data:ema_20_gap_pct', TRUE),
    ('macd_hist_pct', 'MACD Histogram %', 'technical', 'twelve_data', 'twelve_data:macd_hist_pct', TRUE)
ON CONFLICT (name) DO UPDATE
SET
    display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    source = EXCLUDED.source,
    link = EXCLUDED.link,
    active = EXCLUDED.active;

INSERT INTO technical_indicator_rules (
    indicator,
    range_min,
    range_max,
    score,
    trend,
    interpretation,
    action,
    score_mode,
    weight,
    is_active,
    user_id
) VALUES
    ('ema_20_gap_pct', 0, 20, 10, 'zeer zwak', 'Prijs noteert duidelijk onder de EMA20. Korte-termijn momentum is zwak.', 'Actie: defensief. Wacht op herstel boven trendbasis of sterkere bevestiging.', 'standard', 1.0, TRUE, NULL),
    ('ema_20_gap_pct', 20, 40, 25, 'zwak', 'Prijs ligt licht onder de EMA20. Trend is nog kwetsbaar.', 'Actie: voorzichtig. Alleen selectieve setups met strak risico.', 'standard', 1.0, TRUE, NULL),
    ('ema_20_gap_pct', 40, 60, 50, 'neutraal', 'Prijs zit rond de EMA20. Korte-termijn richting is gemengd.', 'Actie: neutraal. Wacht op uitbrekend momentum of duidelijkere trend.', 'standard', 1.0, TRUE, NULL),
    ('ema_20_gap_pct', 60, 80, 75, 'sterk', 'Prijs noteert boven de EMA20. Korte-termijn trend ondersteunt long-bias.', 'Actie: pro-trend. Trend-following setups krijgen meer kwaliteit.', 'standard', 1.0, TRUE, NULL),
    ('ema_20_gap_pct', 80, 100, 100, 'extreem', 'Prijs noteert fors boven de EMA20. Trend is sterk, maar let op overextensie.', 'Actie: sterk momentum, maar manage winst en chase niet blind.', 'standard', 1.0, TRUE, NULL),

    ('macd_hist_pct', 0, 20, 10, 'zeer zwak', 'MACD histogram is duidelijk negatief. Momentum verslechtert.', 'Actie: defensief. Vermijd agressieve longs tot momentum draait.', 'standard', 1.0, TRUE, NULL),
    ('macd_hist_pct', 20, 40, 25, 'zwak', 'MACD histogram blijft negatief, maar minder extreem.', 'Actie: voorzichtig. Bevestiging nodig voordat trendposities logisch worden.', 'standard', 1.0, TRUE, NULL),
    ('macd_hist_pct', 40, 60, 50, 'neutraal', 'MACD histogram zit rond nul. Momentum is onbeslist.', 'Actie: neutraal. Focus op structuur, niet op alleen momentum.', 'standard', 1.0, TRUE, NULL),
    ('macd_hist_pct', 60, 80, 75, 'sterk', 'MACD histogram is positief. Momentum bouwt op.', 'Actie: pro-trend. Long-bias krijgt steun zolang dit aanhoudt.', 'standard', 1.0, TRUE, NULL),
    ('macd_hist_pct', 80, 100, 100, 'extreem', 'MACD histogram is zeer sterk positief. Momentum versnelt hard.', 'Actie: sterk momentum, maar bewaak oververhitting en neem discipline mee.', 'standard', 1.0, TRUE, NULL)
ON CONFLICT DO NOTHING;
"""
