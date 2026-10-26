"""Keep the first Paper exit release reversible to the previous bot writer."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_expand_release_preserves_legacy_writer_and_disables_exits():
    migration = (ROOT / "backend/trading-tool-backend/backend/scripts/migrations"
                 / "2026_10_26_paper_exit_decision_identity.py").read_text()
    engine = (ROOT / "backend/trading-tool-backend/backend/engine"
              / "trading_bot_execution.py").read_text()
    deploy = (ROOT / "ops/deploy/deploy_env.sh").read_text()
    rollback = (ROOT / "ops/deploy/rollback_env.sh").read_text()

    assert "ADD COLUMN IF NOT EXISTS decision_kind" in migration
    assert "DROP CONSTRAINT" not in migration
    assert "DROP INDEX" not in migration
    assert "PAPER_AUTO_EXIT_CUTOVER = False" in engine
    assert "if PAPER_AUTO_EXIT_CUTOVER else None" in engine
    assert "paper_exit_decision_expand" in deploy
    assert "paper_exit_writer_quiesce" not in deploy
    assert '"$paper_exit_schema_state" != expanded' in rollback
