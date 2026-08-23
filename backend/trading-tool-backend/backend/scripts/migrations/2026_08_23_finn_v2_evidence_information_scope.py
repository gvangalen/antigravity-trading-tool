"""Persist the canonical InformationScope on FINN V2 evidence artifacts."""

SQL = """
ALTER TABLE finn_v2_evidence_artifacts
    ADD COLUMN IF NOT EXISTS information_scope TEXT NULL;

UPDATE finn_v2_evidence_artifacts
SET information_scope = CASE tool_name
    WHEN 'read_profile' THEN 'profile'
    WHEN 'read_user_preferences' THEN 'preferences'
    WHEN 'read_active_asset' THEN 'active_asset'
    WHEN 'read_indicator_configuration' THEN 'indicator_configuration'
    WHEN 'read_asset_scores' THEN 'market_snapshot'
    WHEN 'read_market_snapshot' THEN 'market_snapshot'
    WHEN 'read_macro_snapshot' THEN 'market_snapshot'
    WHEN 'read_technical_snapshot' THEN 'market_snapshot'
    WHEN 'read_active_setup' THEN 'active_setup'
    WHEN 'read_linked_strategy' THEN 'linked_strategy'
    WHEN 'read_linked_bot' THEN 'linked_bot'
    WHEN 'read_bot_status' THEN 'bot_status'
    WHEN 'read_watchlist' THEN 'watchlist'
    WHEN 'read_portfolio' THEN 'profile'
    WHEN 'read_latest_report' THEN 'market_snapshot'
    WHEN 'read_review_history' THEN 'profile'
    ELSE information_scope
END
WHERE information_scope IS NULL;

CREATE INDEX IF NOT EXISTS idx_finn_v2_evidence_information_scope
    ON finn_v2_evidence_artifacts (information_scope);

ALTER TABLE finn_v2_evidence_artifacts
    DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope;

ALTER TABLE finn_v2_evidence_artifacts
    ADD CONSTRAINT ck_finn_v2_evidence_information_scope
    CHECK (information_scope IS NULL OR information_scope IN (
        'capability', 'profile', 'preferences', 'active_asset',
        'indicator_configuration', 'market_snapshot', 'watchlist',
        'active_setup', 'linked_strategy', 'linked_bot', 'bot_status'
    ));
"""


ROLLBACK_SQL = """
ALTER TABLE finn_v2_evidence_artifacts
    DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope;
DROP INDEX IF EXISTS idx_finn_v2_evidence_information_scope;
ALTER TABLE finn_v2_evidence_artifacts
    DROP COLUMN IF EXISTS information_scope;
"""
