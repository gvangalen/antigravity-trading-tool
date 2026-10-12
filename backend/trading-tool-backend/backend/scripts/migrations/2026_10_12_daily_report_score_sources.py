"""Keep the score-source moments used by each saved daily report."""

SQL = """
ALTER TABLE daily_reports
    ADD COLUMN IF NOT EXISTS score_source_snapshot JSONB;
"""
