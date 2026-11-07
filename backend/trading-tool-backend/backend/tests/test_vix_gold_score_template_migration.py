import re
from pathlib import Path

from backend.services.indicator_config_service import IndicatorConfigService
from backend.utils.macro_interpreter import normalize_macro_value


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "backend/trading-tool-backend/backend/scripts/migrations/2026_11_07_vix_gold_score_templates.py"
DEPLOY = ROOT / "ops/deploy/deploy_env.sh"


def test_selectable_vix_and_gold_have_complete_deployed_default_rules():
    source = MIGRATION.read_text(encoding="utf-8")
    for indicator in ("vix", "gold_price"):
        buckets = [(int(low), int(high)) for low, high in re.findall(
            rf"\('{indicator}',\s*(\d+),\s*(\d+),", source
        )]
        assert buckets == [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)]
        assert IndicatorConfigService._has_complete_rules([
            {"range_min": low, "range_max": high, "is_active": True}
            for low, high in buckets
        ])
    assert "existing.user_id IS NULL" in source
    assert "WHERE NOT EXISTS" in source
    assert "DELETE FROM" not in source
    assert "UPDATE macro_indicator_rules" not in source
    assert f"run_migration backend/scripts/migrations/{MIGRATION.name}" in DEPLOY.read_text(encoding="utf-8")


def test_vix_levels_reach_the_intended_low_and_high_volatility_buckets():
    assert normalize_macro_value("vix", 10) == 0
    assert normalize_macro_value("vix", 25) == 50
    assert normalize_macro_value("vix", 40) == 100
