"""Review index preflight must never build on the write-locked ledger."""

import runpy
from pathlib import Path

from backend.scripts import create_finn_trade_review_ledger_index as index_job


def test_concurrent_index_preflight_uses_autocommit_and_recovers_invalid_index(monkeypatch):
    calls = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql, params=None):
            assert connection.autocommit is True
            calls.append((sql, params))

        def fetchone(self):
            return False, "bot_ledger"

    class Connection:
        autocommit = False

        def cursor(self):
            return Cursor()

        def close(self):
            calls.append(("closed", None))

    connection = Connection()
    monkeypatch.setattr(index_job, "get_db_connection", lambda: connection)
    index_job.run()
    sql = "\n".join(str(item[0]) for item in calls)
    assert sql.index("DROP INDEX CONCURRENTLY") < sql.index("CREATE INDEX CONCURRENTLY")
    assert "CREATE INDEX CONCURRENTLY" in sql
    assert connection.autocommit is True


def test_transactional_review_migration_does_not_build_ledger_index():
    migration = Path(__file__).parents[1] / "scripts/migrations/2026_10_16_finn_trade_reviews.py"
    sql = runpy.run_path(str(migration))["SQL"]
    assert "ix_finn_trade_review_ledger_user_cursor" not in sql
    assert "LOCK TABLE bot_ledger" in sql  # bounded cutover baseline lock remains
    assert "trg_finn_trade_review_decision_dirty" in sql


def test_reflection_memory_migration_preserves_unknown_legacy_message_revision():
    migration = Path(__file__).parents[1] / "scripts/migrations/2026_10_22_finn_trade_reflection_memory.py"
    sql = runpy.run_path(str(migration))["SQL"]
    assert "ADD COLUMN IF NOT EXISTS input_revision BIGINT NULL" in sql
    assert "UPDATE finn_trade_review_messages SET input_revision" not in sql
    assert "PRIMARY KEY (user_id,review_id)" in sql
    assert "evidence_revision BIGINT NOT NULL" in sql
