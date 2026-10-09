"""Remove the unused pre-Score-2.0 insight view and narrative store."""

SQL = """
DROP VIEW IF EXISTS ai_master_score_view;
DROP TABLE IF EXISTS ai_category_insights;
"""
