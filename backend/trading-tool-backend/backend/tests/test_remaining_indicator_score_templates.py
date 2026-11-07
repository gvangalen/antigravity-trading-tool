"""The selectable catalog must have deployed rules for every indicator."""

import re
from pathlib import Path

from backend.domain.macro_indicator_catalog import get_active_macro_indicator_definitions
from backend.domain.technical_indicator_catalog import get_active_technical_indicator_definitions
from backend.domain.market_indicator_catalog import get_active_market_indicator_definitions
from backend.utils.macro_interpreter import normalize_macro_value


ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS = ROOT / "backend/trading-tool-backend/backend/scripts/migrations"
DEPLOY = ROOT / "ops/deploy/deploy_env.sh"


def test_every_active_catalog_indicator_has_a_deployed_five_bucket_template():
    deployed = re.findall(r"run_migration backend/scripts/migrations/([^\s]+\.py)",
                          DEPLOY.read_text(encoding="utf-8"))
    sql = "\n".join((MIGRATIONS / name).read_text(encoding="utf-8")
                    for name in deployed if "score_template" in name)
    definitions = (get_active_market_indicator_definitions()
                   + get_active_macro_indicator_definitions()
                   + get_active_technical_indicator_definitions())
    assert len(definitions) == 21
    for definition in definitions:
        name = definition["name"]
        assert re.search(rf"'{re.escape(name)}'", sql), name
    remaining = (MIGRATIONS / "2026_11_07_remaining_indicator_score_templates.py").read_text()
    for name in ("etf_bitcoin_inflow", "oil_price", "us10y", "us02y",
                 "interest_rate", "inflation_rate", "adx", "atr_pct",
                 "ema_20_gap_pct", "ema_50_gap_pct"):
        assert f"('{name}'" in remaining
    assert "(0, 20," in remaining and "(80, 100," in remaining
    assert "existing.user_id IS NULL" in remaining
    assert "WHERE NOT EXISTS" in remaining


def test_rate_and_inflation_inputs_reach_middle_buckets():
    assert normalize_macro_value("us02y", 5) == 50
    assert normalize_macro_value("interest_rate", 5) == 50
    assert normalize_macro_value("inflation_rate", 5) == 50
