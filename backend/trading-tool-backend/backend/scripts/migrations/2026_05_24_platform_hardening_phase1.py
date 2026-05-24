"""Platform hardening phase 1 database invariants.

Run this SQL before deploying cache code that uses
ON CONFLICT (query_hash, symbol, timeframe, category).
"""

SQL = """
ALTER TABLE ai_response_cache
DROP CONSTRAINT IF EXISTS ai_response_cache_query_hash_key;

DROP INDEX IF EXISTS ai_response_cache_query_hash_key;

CREATE UNIQUE INDEX IF NOT EXISTS ux_ai_response_cache_context
ON ai_response_cache (query_hash, symbol, timeframe, category);

CREATE UNIQUE INDEX IF NOT EXISTS ux_conversation_state_user_id
ON conversation_state (user_id);
"""
