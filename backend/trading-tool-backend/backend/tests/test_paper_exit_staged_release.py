"""Require a writer drain before the Paper exit identity cutover."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]


def test_cutover_drains_old_writers_before_enabling_position_exits():
    expand = (ROOT / "backend/trading-tool-backend/backend/scripts/migrations"
                 / "2026_10_26_paper_exit_decision_identity.py").read_text()
    cutover = (ROOT / "backend/trading-tool-backend/backend/scripts/migrations"
               / "2026_10_27_paper_exit_cutover.py").read_text()
    engine = (ROOT / "backend/trading-tool-backend/backend/engine"
              / "trading_bot_execution.py").read_text()
    deploy = (ROOT / "ops/deploy/deploy_env.sh").read_text()
    rollback = (ROOT / "ops/deploy/rollback_env.sh").read_text()

    assert "ADD COLUMN IF NOT EXISTS decision_kind" in expand
    assert "DROP CONSTRAINT" not in expand
    assert "DROP INDEX" not in expand
    assert "paper_exit_expand_required" in cutover
    assert "DROP CONSTRAINT" in cutover
    assert "DROP INDEX" in cutover
    assert "PAPER_AUTO_EXIT_CUTOVER = True" in engine
    assert "if PAPER_AUTO_EXIT_CUTOVER else None" in engine
    assert "paper_exit_decision_expand" in deploy
    assert "paper_exit_writer_quiesce" in deploy
    assert "paper_exit_old_writers_still_online" in deploy
    assert "2026_10_27_paper_exit_cutover.py" in deploy
    assert deploy.index("paper_exit_writer_quiesce") < deploy.index("paper_exit_decision_cutover")
    assert deploy.index("paper_exit_decision_cutover") < deploy.index("PM2_DEPLOY_MODE=phased", deploy.index("paper_exit_decision_cutover"))
    assert '"$paper_exit_schema_state" != expanded' in rollback
