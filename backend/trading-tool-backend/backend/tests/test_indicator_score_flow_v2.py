"""The selected indicator, its personal rule, and the category use one value."""

from datetime import datetime, timedelta, timezone

from backend.utils import scoring_utils
from backend.utils.market_interpreter import normalize_market_value, normalize_market_value_with_history


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params):
        if "SELECT indicator FROM user_indicator_configs" in sql:
            self.rows = [("dxy",), ("fear_greed_index",)]
        elif "FROM macro_data" in sql and "source_observed_at::date" in sql:
            now = datetime.now(timezone.utc)
            self.rows = [((now - timedelta(days=index)).date(), value)
                         for index, value in enumerate((90, 95, 100, 105, 110))]
        elif "SELECT DISTINCT ON" in sql:
            now = datetime.now(timezone.utc)
            self.rows = [("dxy", 100, now), ("fear_greed_index", 30, now)]
        elif "SELECT id, config_json, priority FROM user_indicator_configs" in sql:
            indicator = params[-1]
            if indicator == "dxy":
                rules = [
                    {"range_min": lower, "range_max": upper, "score": score}
                    for lower, upper, score in (
                        (0, 20, 10), (20, 40, 25), (40, 60, 80),
                        (60, 80, 75), (80, 100, 100),
                    )
                ]
                self.rows = [(1, {"score_mode": "custom", "weight": 2, "rules": rules}, 100)]
            else:
                self.rows = [(2, {"score_mode": "standard", "weight": 1}, 100)]
        elif "FROM macro_indicator_rules" in sql:
            self.rows = [
                (index, "fear_greed_index", lower, upper, score, None, None,
                 None, "standard", True, 1, None)
                for index, (lower, upper, score) in enumerate(
                    ((0, 20, 10), (20, 40, 25), (40, 60, 50),
                     (60, 80, 75), (80, 100, 100)), 1
                )
            ]
        else:
            raise AssertionError(sql)

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def cursor(self):
        return _Cursor(self)

    def close(self):
        pass


def test_personal_indicator_rules_feed_weighted_macro_score(monkeypatch):
    monkeypatch.setattr(scoring_utils, "get_db_connection", _Connection)

    result = scoring_utils.generate_scores_db("macro", user_id=7, symbol="BTC")

    assert result["source_status"] == "available"
    assert result["scores"]["dxy"]["value"] == 100
    assert result["scores"]["dxy"]["normalized_value"] == 50
    assert result["scores"]["dxy"]["score"] == 80
    assert result["scores"]["dxy"]["weight"] == 2
    assert result["scores"]["fear_greed_index"]["score"] == 25
    assert result["total_score"] == 62


def test_absolute_macro_level_without_dated_history_is_not_scored(monkeypatch):
    class ShortHistoryConnection(_Connection):
        def cursor(self):
            cursor = super().cursor()
            original = cursor.execute

            def execute(sql, params):
                original(sql, params)
                if "FROM macro_data" in sql and "source_observed_at::date" in sql:
                    cursor.rows = cursor.rows[:2]

            cursor.execute = execute
            return cursor

    monkeypatch.setattr(scoring_utils, "get_db_connection", ShortHistoryConnection)
    result = scoring_utils.generate_scores_db("macro", user_id=7, symbol="BTC")
    assert result["scores"] == {}
    assert result["source_status"] == "insufficient_indicator_history"


def test_market_change_keeps_direction_before_rule_bucket_selection():
    assert normalize_market_value("change_24h", -10) == 25
    assert normalize_market_value("change_24h", 0) == 50
    assert normalize_market_value("change_24h", 10) == 75


def test_missing_selected_indicator_does_not_reweight_category(monkeypatch):
    class MissingConnection(_Connection):
        def cursor(self):
            cursor = super().cursor()
            original = cursor.execute

            def execute(sql, params):
                original(sql, params)
                if "SELECT DISTINCT ON" in sql:
                    cursor.rows = cursor.rows[:1]

            cursor.execute = execute
            return cursor

    monkeypatch.setattr(scoring_utils, "get_db_connection", MissingConnection)

    result = scoring_utils.generate_scores_db("macro", user_id=7, symbol="BTC")

    assert result["source_status"] == "missing_or_stale_indicator"
    assert result["scores"] == {}


def test_absolute_market_price_and_volume_need_asset_history():
    class HistoryCursor:
        def __init__(self, rows):
            self.rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            assert params == ("BTC",)
            assert "FROM market_data" in sql

        def fetchall(self):
            return [(value,) for value in self.rows]

    class HistoryConnection:
        def __init__(self, rows):
            self.rows = rows

        def cursor(self):
            return HistoryCursor(self.rows)

    assert normalize_market_value_with_history(
        HistoryConnection([40_000, 50_000, 60_000, 70_000, 80_000]),
        "BTC", "price", 60_000,
    ) == 50
    assert normalize_market_value_with_history(
        HistoryConnection([100, 100, 100, 100, 100]), "BTC", "volume", 150,
    ) == 75
    assert normalize_market_value_with_history(
        HistoryConnection([60_000]), "BTC", "price", 60_000,
    ) is None


def test_snapshot_is_invalid_after_rule_or_source_changes():
    now = datetime.now(timezone.utc)
    observed = now - timedelta(hours=1)
    saved = {"rsi": {"value": 48, "source_observed_at": observed.isoformat()}}
    readings = [("rsi", 48, observed)]

    assert scoring_utils.score_snapshot_is_current(
        "technical", "BTC", [("rsi", now - timedelta(minutes=2))],
        readings, saved, now,
    ) is True
    assert scoring_utils.score_snapshot_is_current(
        "technical", "BTC", [("rsi", now + timedelta(seconds=1))],
        readings, saved, now,
    ) is False
    assert scoring_utils.score_snapshot_is_current(
        "technical", "BTC", [("rsi", now - timedelta(minutes=2))],
        [("rsi", 49, observed)], saved, now,
    ) is False
