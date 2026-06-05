"""Add idempotency support for bot-generated executions and execute-ledger rows.

Run this SQL before deploying execution paths that rely on
ON CONFLICT (user_id, bot_order_id) and execute-ledger replay guards.
"""

SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_executions_user_order
ON bot_executions (user_id, bot_order_id);

CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_ledger_execute_user_order
ON bot_ledger (user_id, order_id, entry_type)
WHERE entry_type = 'execute' AND order_id IS NOT NULL;
"""
