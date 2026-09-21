"""Allow canonical live macro and technical evidence scopes."""

SQL = """
ALTER TABLE finn_v2_evidence_artifacts
    DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope;

ALTER TABLE finn_v2_evidence_artifacts
    ADD CONSTRAINT ck_finn_v2_evidence_information_scope
    CHECK (information_scope IS NULL OR information_scope IN (
        'capability', 'profile', 'preferences', 'active_asset',
        'indicator_configuration', 'market_snapshot', 'macro_snapshot',
        'technical_snapshot', 'watchlist', 'active_setup', 'linked_strategy',
        'linked_bot', 'bot_status', 'scores', 'portfolio', 'latest_report',
        'review_history'
    ));
"""

ROLLBACK_SQL = """
ALTER TABLE finn_v2_evidence_artifacts
    DROP CONSTRAINT IF EXISTS ck_finn_v2_evidence_information_scope;
"""
