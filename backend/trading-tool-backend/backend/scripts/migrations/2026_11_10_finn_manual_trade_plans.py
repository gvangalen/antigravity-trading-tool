"""Store confirmed, non-executable FINN manual trade plans by owner and run."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_manual_trade_plans (
    id VARCHAR PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_run_id VARCHAR NOT NULL,
    plan_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_finn_manual_trade_plan_owner_run UNIQUE (user_id, source_run_id),
    CONSTRAINT ck_finn_manual_trade_plan_not_executable
      CHECK (plan_json->>'executable' = 'false')
);
CREATE INDEX IF NOT EXISTS ix_finn_manual_trade_plans_user_created
    ON finn_manual_trade_plans (user_id, created_at DESC);
"""
