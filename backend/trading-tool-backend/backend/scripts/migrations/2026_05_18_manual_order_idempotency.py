"""Add idempotency support for manual bot orders.

Run the SQL in this file against the target PostgreSQL database before deploying
backend code that writes BotManualOrderSchema.idempotency_key.
"""

SQL = """
ALTER TABLE bot_orders
ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_orders_user_idempotency_key
ON bot_orders (user_id, idempotency_key)
WHERE idempotency_key IS NOT NULL;
"""
