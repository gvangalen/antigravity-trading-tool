"""Remove the unused pre-Score-2.0 narrative insight store."""

SQL = """
DROP TABLE IF EXISTS ai_category_insights;
"""
