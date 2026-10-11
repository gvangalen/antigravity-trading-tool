"""Keep simulated Paper funding separate from configured bot spending limits."""

SQL = """
ALTER TABLE bot_configs
    ADD COLUMN IF NOT EXISTS paper_initial_cash_eur NUMERIC(18, 2) NOT NULL DEFAULT 0;

ALTER TABLE bot_configs
    DROP CONSTRAINT IF EXISTS bot_configs_paper_initial_cash_nonnegative;
ALTER TABLE bot_configs
    ADD CONSTRAINT bot_configs_paper_initial_cash_nonnegative
    CHECK (paper_initial_cash_eur >= 0);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_ledger_paper_initial_funding
ON bot_ledger (user_id, bot_id, entry_type)
WHERE entry_type = 'paper_initial_funding';
"""
