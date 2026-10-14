"""Persist order environment and exchange identity for safe settlement.

Historical order environments stay NULL because current bot mode cannot prove
whether an older fill was Paper or Live.
"""

SQL = """
ALTER TABLE bot_orders ADD COLUMN IF NOT EXISTS execution_environment TEXT;
ALTER TABLE bot_orders ADD COLUMN IF NOT EXISTS exchange_order_id TEXT;
ALTER TABLE bot_orders ADD COLUMN IF NOT EXISTS exchange_name TEXT;
ALTER TABLE bot_orders ADD COLUMN IF NOT EXISTS exchange_symbol TEXT;
ALTER TABLE bot_ledger ADD COLUMN IF NOT EXISTS fill_sequence INTEGER NOT NULL DEFAULT 0;

ALTER TABLE bot_orders DROP CONSTRAINT IF EXISTS bot_orders_status_check;
ALTER TABLE bot_orders ADD CONSTRAINT bot_orders_status_check CHECK (
  status IN ('ready', 'approved', 'pending', 'sending', 'sent',
             'unknown_exchange_state', 'filled', 'partial', 'cancelled',
             'rejected', 'error', 'failed')
);
ALTER TABLE bot_decisions DROP CONSTRAINT IF EXISTS bot_decisions_status_check;
ALTER TABLE bot_decisions ADD CONSTRAINT bot_decisions_status_check CHECK (
  status IN ('planned', 'ready', 'approved', 'executing', 'awaiting_exchange',
             'unknown_exchange_state', 'executed', 'skipped', 'failed', 'failed_execution')
);
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'bot_orders_execution_environment_check') THEN
    ALTER TABLE bot_orders ADD CONSTRAINT bot_orders_execution_environment_check
      CHECK (execution_environment IN ('paper', 'live'));
  END IF;
END $$;

DROP INDEX IF EXISTS ux_bot_ledger_execute_user_order;
CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_ledger_execute_user_order_fill
ON bot_ledger (user_id, order_id, entry_type, fill_sequence)
WHERE entry_type = 'execute' AND order_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_bot_orders_live_unsettled
ON bot_orders (created_at, id)
WHERE execution_environment='live' AND status='sent';
"""
