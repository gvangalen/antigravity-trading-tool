"""Align the bot table with the mode accepted by FINN and the bot API.

The original table constraint allowed ``semi`` while both current clients and
BotService persist ``semi-auto``. Keep existing bots and normalize old rows.
"""

SQL = """
ALTER TABLE bot_configs DROP CONSTRAINT IF EXISTS bot_configs_mode_check;
UPDATE bot_configs SET mode = 'semi-auto' WHERE mode = 'semi';
ALTER TABLE bot_configs ADD CONSTRAINT bot_configs_mode_check
    CHECK (mode IN ('manual', 'semi-auto', 'auto'));
"""

ROLLBACK_SQL = """
ALTER TABLE bot_configs DROP CONSTRAINT IF EXISTS bot_configs_mode_check;
UPDATE bot_configs SET mode = 'semi' WHERE mode = 'semi-auto';
ALTER TABLE bot_configs ADD CONSTRAINT bot_configs_mode_check
    CHECK (mode IN ('manual', 'semi', 'auto'));
"""
