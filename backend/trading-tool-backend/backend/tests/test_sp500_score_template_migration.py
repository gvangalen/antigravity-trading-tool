import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
MIGRATION = ROOT / "backend/trading-tool-backend/backend/scripts/migrations/2026_10_18_sp500_score_template.py"
DEPLOY = ROOT / "ops/deploy/deploy_env.sh"


def test_sp500_template_covers_all_normalized_buckets_without_replacing_user_rules():
    source = MIGRATION.read_text(encoding="utf-8")
    buckets = [tuple(map(int, match)) for match in re.findall(
        r"^\s+\((\d+), (\d+), (\d+), '[^']+', '[^']+'\),?$", source,
        flags=re.MULTILINE,
    )]
    assert buckets == [(0, 20, 20), (20, 40, 35), (40, 60, 50),
                       (60, 80, 65), (80, 100, 80)]
    assert "existing.user_id IS NULL" in source
    assert "WHERE NOT EXISTS" in source
    assert "DELETE FROM" not in source
    assert "UPDATE macro_indicator_rules" not in source
    assert "run_migration backend/scripts/migrations/2026_10_18_sp500_score_template.py" in DEPLOY.read_text(encoding="utf-8")
