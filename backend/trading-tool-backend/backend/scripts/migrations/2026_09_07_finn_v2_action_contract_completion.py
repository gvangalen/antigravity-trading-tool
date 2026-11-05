"""Complete the FINN V2 V1 mutation invariants without copying user state.

The cleanup retains the oldest canonical watchlist row per user and symbol.
The unique index is then the authoritative concurrency guard; adapters use
``ON CONFLICT`` so repeated confirmations cannot create another record.
"""

SQL = """
-- The prior migration added a narrower check before the V1 contract scopes
-- existed. Release databases can therefore contain legacy aliases that need
-- normalizing. Remove that old check before rewriting those rows, then add
-- the complete canonical allowlist atomically in this migration transaction.
ALTER TABLE finn_v2_evidence_artifacts
    DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope;

UPDATE finn_v2_evidence_artifacts
SET information_scope = CASE tool_name
    WHEN 'read_asset_scores' THEN 'scores'
    WHEN 'read_portfolio' THEN 'portfolio'
    WHEN 'read_latest_report' THEN 'latest_report'
    WHEN 'read_review_history' THEN 'review_history'
    ELSE information_scope
END
WHERE tool_name IN (
    'read_asset_scores',
    'read_portfolio',
    'read_latest_report',
    'read_review_history'
);

ALTER TABLE finn_v2_evidence_artifacts
    ADD CONSTRAINT ck_finn_v2_evidence_information_scope
    CHECK (information_scope IS NULL OR information_scope IN (
        'capability', 'profile', 'preferences', 'active_asset',
        'indicator_configuration', 'market_snapshot', 'macro_snapshot',
        'technical_snapshot', 'watchlist',
        'active_setup', 'linked_strategy', 'linked_bot', 'bot_status',
        'scores', 'portfolio', 'latest_report', 'review_history'
    ));

DO $$
BEGIN
    -- Pair-aware watchlists deliberately contain more than one row per base
    -- symbol. Deploy replays this migration, so never deduplicate those rows
    -- or recreate the legacy base-symbol constraint after the pair cutover.
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'watchlists' AND column_name = 'market_id'
    ) THEN
        DELETE FROM watchlists duplicate
        USING watchlists canonical
        WHERE duplicate.user_id = canonical.user_id
          AND duplicate.symbol = canonical.symbol
          AND duplicate.id > canonical.id;

        IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ux_watchlists_user_symbol'
          AND conrelid = 'watchlists'::regclass
        ) THEN
            ALTER TABLE watchlists
                ADD CONSTRAINT ux_watchlists_user_symbol UNIQUE (user_id, symbol);
        END IF;
    END IF;
END $$;
"""

ROLLBACK_SQL = """
ALTER TABLE watchlists DROP CONSTRAINT IF EXISTS ux_watchlists_user_symbol;
"""
