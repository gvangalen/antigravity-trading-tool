from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.utils.technical_interpreter import normalize_technical_value, normalize_technical_value_for_rules


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "backend/trading-tool-backend/backend/scripts/migrations/2026_10_26_ma50_macd_score_templates.py"
DEPLOY = ROOT / "ops/deploy/deploy_env.sh"


def test_ma50_standard_score_keeps_above_below_direction():
    assert normalize_technical_value("ma_50", 0.90) < 50
    assert normalize_technical_value("ma_50", 1.00) == 50
    assert normalize_technical_value("ma_50", 1.10) > 50


def test_existing_custom_ma50_distance_curve_retains_original_input(monkeypatch):
    from backend.utils import scoring_engine

    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: [
        SimpleNamespace(score_mode="custom")
    ])
    assert normalize_technical_value_for_rules(object(), "ma_50", 0.96, 7, "AAPL") == pytest.approx(26.6666667)
    assert normalize_technical_value_for_rules(object(), "ma_50", 1.04, 7, "AAPL") == pytest.approx(26.6666667)


def test_templates_preserve_owner_curves_and_are_deployed():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "('ma_50'), ('macd_hist_pct')" in source
    assert "existing.user_id IS NULL" in source
    assert "WHERE NOT EXISTS" in source
    assert "DELETE FROM" not in source
    assert "UPDATE technical_indicator_rules" not in source
    assert f"run_migration backend/scripts/migrations/{MIGRATION.name}" in DEPLOY.read_text(encoding="utf-8")
