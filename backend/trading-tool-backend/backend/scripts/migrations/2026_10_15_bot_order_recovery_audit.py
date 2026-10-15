"""Audit manual recovery of an exchange submission with an uncertain outcome."""

SQL = """
CREATE TABLE IF NOT EXISTS bot_order_recovery_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    order_id INTEGER NOT NULL REFERENCES bot_orders(id),
    action TEXT NOT NULL CHECK (action IN ('attach_exchange_order', 'verified_no_order')),
    exchange_order_id TEXT,
    operator_id TEXT NOT NULL,
    evidence_reference TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_bot_order_recovery_events_order
ON bot_order_recovery_events (user_id, order_id, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_bot_orders_live_retry
ON bot_orders ((COALESCE(updated_at, created_at)), id)
WHERE execution_environment='live' AND status='sent';
CREATE UNIQUE INDEX IF NOT EXISTS ux_bot_orders_exchange_identity
ON bot_orders (user_id, exchange_name, exchange_order_id)
WHERE exchange_order_id IS NOT NULL;
"""
