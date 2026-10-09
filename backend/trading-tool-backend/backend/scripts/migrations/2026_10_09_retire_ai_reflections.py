"""Remove the retired per-indicator AI reflection table.

FINN Today and conversational reviews use plan context and product activity;
neither reads or writes this legacy table.
"""

SQL = """
DROP TABLE IF EXISTS ai_reflections;
"""
