from pathlib import Path

from sqlalchemy import UniqueConstraint

from backend.infrastructure.models import Watchlist


ROOT = Path(__file__).resolve().parents[1]


def test_action_contract_completion_migration_repairs_scope_values_and_watchlist_uniqueness():
    source = (ROOT / "scripts" / "migrations" / "2026_09_07_finn_v2_action_contract_completion.py").read_text(
        encoding="utf-8"
    )

    assert "WHEN 'read_asset_scores' THEN 'scores'" in source
    assert "WHEN 'read_portfolio' THEN 'portfolio'" in source
    assert "DELETE FROM watchlists duplicate" in source
    assert "ADD CONSTRAINT ux_watchlists_user_symbol UNIQUE (user_id, symbol)" in source
    assert "DROP CONSTRAINT IF EXISTS ux_watchlists_user_symbol" in source


def test_watchlist_model_declares_the_same_database_idempotency_constraint():
    constraints = [constraint for constraint in Watchlist.__table__.constraints if isinstance(constraint, UniqueConstraint)]

    assert any(
        constraint.name == "ux_watchlists_user_symbol"
        and tuple(column.name for column in constraint.columns) == ("user_id", "symbol")
        for constraint in constraints
    )
