"""The movement staging migration must remain separate from trading state."""

import runpy
from pathlib import Path


def test_movement_migration_is_owner_scoped_and_does_not_touch_bot_state():
    root = Path(__file__).parents[1]
    sql = runpy.run_path(str(root / "scripts/migrations/2026_10_18_finn_exchange_movements.py"))["SQL"]
    assert "CREATE TABLE IF NOT EXISTS finn_exchange_import_movements" in sql
    assert "user_id INTEGER NOT NULL REFERENCES users(id)" in sql
    assert "source_id BIGINT NOT NULL REFERENCES finn_exchange_import_sources(id)" in sql
    assert "UNIQUE(user_id, source_id, provider_transaction_id)" in sql
    assert "unsupported_reason TEXT NULL" in sql
    assert "bot_ledger" not in sql and "bot_orders" not in sql and "bot_portfolios" not in sql
