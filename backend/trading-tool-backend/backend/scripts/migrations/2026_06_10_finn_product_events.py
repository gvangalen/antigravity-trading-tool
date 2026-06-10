"""Persist FINN product telemetry so operator views survive process restarts."""

SQL = """
CREATE TABLE IF NOT EXISTS finn_product_events (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id VARCHAR,
    event_name VARCHAR NOT NULL,
    surface VARCHAR NOT NULL DEFAULT 'unknown',
    page VARCHAR,
    asset VARCHAR,
    flow_type VARCHAR,
    action_type VARCHAR,
    report_type VARCHAR,
    decision_id VARCHAR,
    bot_id INTEGER,
    setup_id INTEGER,
    strategy_id INTEGER,
    trace_id VARCHAR,
    prompt_text TEXT,
    next_best_action TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_created_at
ON finn_product_events (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_event_name
ON finn_product_events (event_name);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_user_id
ON finn_product_events (user_id);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_session_id
ON finn_product_events (session_id);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_page
ON finn_product_events (page);

CREATE INDEX IF NOT EXISTS idx_finn_product_events_flow_type
ON finn_product_events (flow_type);
"""
