"""Keep fresh databases compatible with bot decision reads."""

SQL = """
ALTER TABLE bot_decisions
    ADD COLUMN IF NOT EXISTS reason_json JSONB NOT NULL DEFAULT '[]'::jsonb;
"""
