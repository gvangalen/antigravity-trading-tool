"""Persist compact, verified FINN V2 conversation references for follow-up requests."""

SQL = """
ALTER TABLE finn_v2_conversations
ADD COLUMN IF NOT EXISTS context_json JSONB NOT NULL DEFAULT '{}'::jsonb;
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_conversations
DROP COLUMN IF EXISTS context_json;
"""
