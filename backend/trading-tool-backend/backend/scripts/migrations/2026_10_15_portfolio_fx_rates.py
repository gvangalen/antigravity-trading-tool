"""Verified, dated FX rates used only for EUR portfolio valuations."""

SQL = """
CREATE TABLE IF NOT EXISTS portfolio_fx_rates (
    quote_currency TEXT PRIMARY KEY CHECK (quote_currency IN ('USD', 'USDT')),
    eur_per_unit NUMERIC NOT NULL CHECK (eur_per_unit > 0),
    provider TEXT NOT NULL,
    provider_pair TEXT NOT NULL,
    source_price NUMERIC NOT NULL CHECK (source_price > 0),
    observed_at TIMESTAMPTZ NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Older writers keep the default even when they execute during deployment.
ALTER TABLE bot_ledger
    ADD COLUMN IF NOT EXISTS valuation_version SMALLINT NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS idx_bot_ledger_legacy_paper_currency
    ON bot_ledger(user_id, bot_id)
    WHERE entry_type='execute' AND valuation_version < 2;
CREATE TABLE IF NOT EXISTS portfolio_value_snapshots_v2 (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    environment TEXT NOT NULL CHECK (environment = 'paper'),
    bucket TEXT NOT NULL CHECK (bucket IN ('1h', '1d')),
    ts TIMESTAMPTZ NOT NULL,
    equity_eur NUMERIC NOT NULL,
    cash_eur NUMERIC NOT NULL,
    position_value_eur NUMERIC NOT NULL,
    covered_bot_count INTEGER NOT NULL CHECK (covered_bot_count > 0),
    source_min_at TIMESTAMPTZ NOT NULL,
    evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    valuation_version SMALLINT NOT NULL DEFAULT 2 CHECK (valuation_version = 2),
    PRIMARY KEY (user_id, environment, bucket, ts)
);
ALTER TABLE portfolio_value_snapshots_v2
    ADD COLUMN IF NOT EXISTS evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb;
DELETE FROM portfolio_value_snapshots_v2 WHERE evidence_json = '{}'::jsonb;
CREATE INDEX IF NOT EXISTS idx_portfolio_value_v2_owner_history
    ON portfolio_value_snapshots_v2(user_id, environment, bucket, ts DESC);
CREATE TABLE IF NOT EXISTS portfolio_unverified_paper_bots (
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bot_id INTEGER NOT NULL REFERENCES bot_configs(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, bot_id)
);
CREATE TABLE IF NOT EXISTS portfolio_valuation_cutover (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    cutover_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO portfolio_valuation_cutover (singleton) VALUES (TRUE)
ON CONFLICT (singleton) DO NOTHING;
-- Historical Paper fills were not guaranteed to use a EUR-converted quote.
-- Keep their ledgers outside verified totals until individually reconciled.
INSERT INTO portfolio_unverified_paper_bots (user_id, bot_id, reason)
SELECT c.user_id, c.id, 'legacy_paper_fill_currency_unverified'
FROM bot_configs c
LEFT JOIN bot_portfolios p ON p.user_id=c.user_id AND p.bot_id=c.id
JOIN portfolio_valuation_cutover cutover ON cutover.singleton=TRUE
WHERE c.is_live=FALSE AND (
    (p.updated_at < cutover.cutover_at AND
      (COALESCE(p.position_qty,0) <> 0 OR COALESCE(p.invested_eur,0) <> 0
       OR COALESCE(p.realized_pnl_eur,0) <> 0))
    OR EXISTS (SELECT 1 FROM bot_ledger l WHERE l.user_id=c.user_id
               AND l.bot_id=c.id AND l.entry_type='execute' AND l.valuation_version < 2)
)
ON CONFLICT (user_id, bot_id) DO NOTHING;
DELETE FROM portfolio_value_snapshots_v2 s
WHERE EXISTS (
    SELECT 1 FROM portfolio_unverified_paper_bots u WHERE u.user_id=s.user_id
);
"""

ROLLBACK_SQL = "DROP TABLE IF EXISTS portfolio_valuation_cutover; DROP TABLE IF EXISTS portfolio_unverified_paper_bots; DROP TABLE IF EXISTS portfolio_value_snapshots_v2; DROP TABLE IF EXISTS portfolio_fx_rates;"
