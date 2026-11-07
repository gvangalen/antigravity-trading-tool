"""Index minimal web app activity timestamps for bounded admin user pages."""

SQL = """
CREATE INDEX IF NOT EXISTS idx_finn_product_events_web_app_activity_user_time
ON finn_product_events (user_id, created_at DESC)
WHERE event_name = 'app_activity' AND surface = 'web';
"""
