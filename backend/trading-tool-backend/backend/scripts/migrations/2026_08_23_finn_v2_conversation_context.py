"""Persist compact, verified FINN V2 conversation references for follow-up requests."""

SQL = """
ALTER TABLE finn_v2_conversations
ADD COLUMN IF NOT EXISTS context_json JSONB;

UPDATE finn_v2_conversations
SET context_json = '{}'::jsonb
WHERE context_json IS NULL;

ALTER TABLE finn_v2_conversations
ALTER COLUMN context_json SET DEFAULT '{}'::jsonb;

ALTER TABLE finn_v2_conversations
ALTER COLUMN context_json SET NOT NULL;
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_conversations
DROP COLUMN IF EXISTS context_json;
"""
