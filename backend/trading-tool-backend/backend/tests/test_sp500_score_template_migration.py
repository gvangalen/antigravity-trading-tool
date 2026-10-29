import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.utils import scoring_engine, scoring_utils


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


def test_sp500_dated_source_becomes_a_verified_macro_score_only_with_a_rule(monkeypatch):
    observed = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    history = [((observed - timedelta(days=day)).date(), 4800 + day * 10)
               for day in range(63)]
    current_value = history[0][1]

    class Cursor:
        rows = []

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, _params):
            if "SELECT indicator FROM (" in sql and "FROM user_indicator_configs" in sql:
                self.rows = [("sp500",)]
            elif "source_observed_at::date" in sql:
                self.rows = history
            elif "SELECT DISTINCT ON" in sql:
                self.rows = [("sp500", current_value, observed)]
            else:
                raise AssertionError(sql)

        def fetchall(self):
            return self.rows

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(scoring_utils, "get_db_connection", Connection)
    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: [])
    missing = scoring_utils.generate_scores_db("macro", user_id=7, symbol="BTC")
    assert missing["source_status"] == "missing_rule"
    assert missing["total_score"] is None

    bucket_rows = [tuple(map(int, match)) for match in re.findall(
        r"^\s+\((\d+), (\d+), (\d+), '[^']+', '[^']+'\),?$",
        MIGRATION.read_text(encoding="utf-8"), flags=re.MULTILINE,
    )]
    rules = [scoring_engine.RuleRow(
        id=index, indicator="sp500", range_min=minimum, range_max=maximum,
        score=score, trend=None, interpretation="macrocontext", action=None,
        score_mode="standard", is_active=True, weight=1.0, user_id=None,
    ) for index, (minimum, maximum, score) in enumerate(bucket_rows, 1)]
    monkeypatch.setattr(scoring_engine, "fetch_rules_for_indicator", lambda *_args, **_kwargs: rules)
    scored = scoring_utils.generate_scores_db("macro", user_id=7, symbol="BTC")
    assert scored["source_status"] == "available"
    assert scored["scores"]["sp500"]["normalized_value"] == 0
    assert scored["scores"]["sp500"]["score"] == 20
    assert scored["scores"]["sp500"]["rule_origin"] == "system_template"
    assert scored["total_score"] == 20
