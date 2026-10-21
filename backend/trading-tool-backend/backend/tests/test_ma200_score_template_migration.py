from pathlib import Path
from types import SimpleNamespace
import pytest

from backend.utils.technical_interpreter import (
    normalize_technical_value,
    normalize_technical_value_for_rules,
)


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "backend/trading-tool-backend/backend/scripts/migrations/2026_10_21_ma200_score_template.py"
DEPLOY = ROOT / "ops/deploy/deploy_env.sh"


def test_ma200_normalization_preserves_direction():
    assert normalize_technical_value("ma_200", 0.8) == 0
    assert normalize_technical_value("ma_200", 0.96) < 50
    assert normalize_technical_value("ma_200", 1.0) == 50
    assert normalize_technical_value("ma_200", 1.04) > 50
    assert normalize_technical_value("ma_200", 1.2) == 100


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), float("-inf")])
def test_ma200_rejects_non_finite_provider_values(invalid, monkeypatch):
    from backend.utils import scoring_engine

    with pytest.raises(ValueError, match="Non-finite"):
        normalize_technical_value("ma_200", invalid)
    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: [
        SimpleNamespace(score_mode="custom")
    ])
    with pytest.raises(ValueError, match="Non-finite"):
        normalize_technical_value_for_rules(object(), "ma_200", invalid, 7, "BTC")


def test_existing_owner_ma200_curve_keeps_legacy_distance_scale(monkeypatch):
    from backend.utils import scoring_engine

    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: [
        SimpleNamespace(score_mode="custom")
    ])
    assert normalize_technical_value_for_rules(object(), "ma_200", 0.96, 7, "BTC") == pytest.approx(20)
    assert normalize_technical_value_for_rules(object(), "ma_200", 1.04, 7, "BTC") == pytest.approx(20)


def test_ma200_template_is_deployed_without_replacing_owner_rules():
    source = MIGRATION.read_text(encoding="utf-8")
    assert "SELECT 'ma_200'" in source
    assert "existing.user_id IS NULL" in source
    assert "WHERE NOT EXISTS" in source
    assert "DELETE FROM" not in source
    assert "UPDATE technical_indicator_rules" not in source
    assert "run_migration backend/scripts/migrations/2026_10_21_ma200_score_template.py" in DEPLOY.read_text(encoding="utf-8")
